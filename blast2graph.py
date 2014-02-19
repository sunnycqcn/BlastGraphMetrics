#!/usr/bin/env python

# Standard Python libraries
import sys
import argparse
from decimal import Decimal

# Third-party libraries
import networkx as nx


def main(argv=None):
    """Where the magic happens!

    The main() function coordinates calls to all of the other functions in this
    program in the hope that, by their powers combined, useful work will be
    done.

    Args:
        None

    Returns:
        An exit status (hopefully 0)
    """
    if argv is None:
        argv = sys.argv

    args = get_parsed_args()

    met_grf = nx.Graph()  # NetworkX graph with various BLAST-based metrics
    org_ids = set()

    get_self_bit_scores_and_org_ids(met_grf=met_grf, blast_handle=args.blast,
                                    idchar=args.idchar, org_ids=org_ids,
                                    evcol=args.evcol-1, bscol=args.bscol-1,
                                    qlcol=args.qlcol-1, slcol=args.slcol-1)

    args.blast.seek(0)

    get_metrics(met_grf=met_grf, blast_handle=args.blast,
                evcol=args.evcol-1, bscol=args.bscol-1,
                qlcol=args.qlcol-1, slcol=args.slcol-1)

    print_abc_files(met_grf, args.out_pref+"_raw")

    metrics = ['evl', 'bit', 'bpr', 'bsr']

    org_avgs = compute_organism_averages(met_grf=met_grf, metrics=metrics,
                                         idchar=args.idchar, org_ids=org_ids)

    compute_global_averags(org_avgs=org_avgs, metrics=metrics)

    normalize_bit_score_ratios(met_grf=met_grf, metrics=metrics,
                               idchar=args.idchar, org_avgs=org_avgs)

    print_abc_files(met_grf, args.out_pref+"_nrm")


def get_parsed_args():
    """Parse the command line arguments

    Parses command line arguments using the argparse package, which is a
    standard Python module starting with version 2.7.

    Args:
        None, argparse fetches them from user input

    Returns:
        args: An argparse.Namespace object containing the parsed arguments
    """
    parser = argparse.ArgumentParser(
                 description='Generate a set of graphs from a tab-delimited ' +
                             'BLASTP or BLASTN file such that the first two ' +
                             'columns contain the query and subject IDs, ' +
                             'respectively, and the last four columns ' +
                             'contain, in order: E-value, bit score, query ' +
                             'length, subject length')

    # Group: IO options
    parser.add_argument('blast', type=argparse.FileType('r'),
                        help='Tab-delimited BLAST file (comment lines are ' +
                             'okay)')
    parser.add_argument('out_pref',
                        help='Prefix for the MCL-compatible "abc" graph files')

    # Group: Formatting options
    parser.add_argument('--evcol', dest='evcol',
                        action='store', type=int, default=11,
                        help='One-indexed column containing pairwise ' +
                             'E-values (not required if files include ' +
                             'standard header lines) [def=11]')
    parser.add_argument('--bscol', dest='bscol',
                        action='store', type=int, default=12,
                        help='One-indexed column containing pairwise bit ' +
                             'scores (not required if files include ' +
                             'standard header lines) [def=12]')
    parser.add_argument('--qlcol', dest='qlcol',
                        action='store', type=int, default=13,
                        help='One-indexed column containing query lengths ' +
                             '(not required if files include standard ' +
                             'header lines) [def=13]')
    parser.add_argument('--slcol', dest='slcol',
                        action='store', type=int, default=14,
                        help='One-indexed column containing subject lengths ' +
                             '(not required if files include standard ' +
                             'header lines) [def=14]')
    parser.add_argument('--idchar', dest='idchar', action='store', default='|',
                        help='The character used to separate the organism ' +
                             'ID from the rest of the sequence header ' +
                             '[def="|"]')

    # Group: TODO
    parser.add_argument('-m', '--merge', dest='merge',
                        action='store_true', default=False,
                        help='Merge sequences from a single organism when ' +
                             'they have non-overlapping alignments to the ' +
                             'same target sequence')

    args = parser.parse_args()

    return args


def get_self_bit_scores_and_org_ids(
        met_grf, blast_handle, idchar=None, org_ids=None,
        evcol=10, bscol=11, qlcol=12, slcol=13):
    """Get bit scores from full-length self-alignments

    Searches an open file for tab-delimited BLAST hit records where the query
    and reference IDs are identical.  It is important that BLAST is run with
    option "--soft_masking true" or the self-alignments are unlikely to be full
    length.

    BLAST does not guarantee particular boundaries for a given alignment, and
    reciprocal alignments frequently have slightly different boundries and
    scores. Neither is more or less valid, so I see no reason to not use the
    larger of the two. I therefore check to make sure subsequent hits do not
    have a greater score than the ones that have already been found. One
    consequence of this is that the intra- and inter-organism average scores
    can not be calculate on the fly.

    Args:
        bsr_graph: A NetworkX graph data structure (does not need to be empty)
        blast_handle: An open file handle containing self-alignments (can
            contain other alignments and/or comment lines beginning with a hash
            '#' character)
        idchar: Character used to delineate between the organism ID and the
            remainder of the sequence ID
        ord_ids: A Python set variable to which organism IDs will be added
        evcol: Column containing BLAST E-values
        bscol: Column containing BLAST bit scores
        qlcol: Column containing query sequence lengths
        slcol: Column containing subject sequence lengths

    Returns:
        Nothing, the NetworkX graph and organsm IDs set data structures are
        edited in place
    """
    for line in blast_handle:
        temp = line.strip().split()
        if not temp:
            continue
        elif temp[0][0] == "#":
            continue

        if temp[0] == temp[1]:
            seq_id = str(temp[0])
            bit_scr = float(temp[bscol])
            org_ids.add(seq_id.split(idchar)[0])

            if not met_grf.has_node(seq_id):
                met_grf.add_node(seq_id, sbs=bit_scr, org=None)
            elif bit_scr > met_grf.node[seq_id]['sbs']:
                met_grf.node[seq_id]['sbs'] = bit_scr


def get_metrics(met_grf, blast_handle,
                evcol=10, bscol=11, qlcol=12, slcol=13):
    """Get bit scores from full-length alignments between different sequences

    Searches an open file for tab-delimited BLAST hit records where the query
    and reference IDs are not identical. It is important that BLAST is run with
    option "--soft_masking true" or the self-alignments are unlikely to be full
    length.

    BLAST does not guarantee particular boundaries for a given alignment, and
    reciprocal alignments frequently have slightly different boundries and
    scores. Neither is more or less valid, so I see no reason to not use the
    larger of the two. I therefore check to make sure subsequent hits do not
    have a greater score than the ones that have already been found. One
    consequence of this is that the intra- and inter-organism average scores
    can not be calculated on the fly.

    Args:
        bsr_graph: A NetworkX graph data structure containing self-alignment
            scores
        blast_handle: An open file handle containing non-self-alignments (can
            contain other alignments and/or comment lines beginning with a hash
            '#' character)
        evcol: Column containing BLAST E-values
        bscol: Column containing BLAST bit scores
        qlcol: Column containing query sequence lengths
        slcol: Column containing subject sequence lengths

    Returns:
        Nothing, all data structures are edited in place
    """
    for line in blast_handle:
        temp = line.strip().split()
        if not temp:
            continue
        elif temp[0][0] == "#":
            continue

        # I convinced myself that removing self-hits from the graph would
        # results in more accurate intra-/inter-organism averages and improve
        # normalization. They are removed before printing.
        metrics = dict()
        qry_id = str(temp[0])
        ref_id = str(temp[1])
        qry_len = float(temp[qlcol])
        ref_len = float(temp[slcol])
        metrics['bit'] = float(temp[bscol])
        metrics['evl'] = float(-Decimal(temp[evcol]).log10())
        #BLAST 2.2.28+ rounds E-values smaller than 1e-180 to zero
        if metrics['evl'] == float('inf'):
            metrics['evl'] = 181.

        if met_grf.has_node(qry_id) and met_grf.has_node(ref_id):
            # Compute 'bit per base', which should really be per amino acid
            metrics['bpr'] = metrics['bit'] / min(qry_len, ref_len)
            # Compute bit score ratio
            qry_sbs = met_grf.node[qry_id]['sbs']
            ref_sbs = met_grf.node[ref_id]['sbs']
            metrics['bsr'] = metrics['bit'] / min(qry_sbs, ref_sbs)

        if not met_grf.has_edge(qry_id, ref_id):
            met_grf.add_edge(qry_id, ref_id)
            for met in metrics.keys():
                met_grf[qry_id][ref_id][met] = metrics[met]

        # Best bit score = best hit
        elif metrics['bit'] > met_grf[qry_id][ref_id]['bit']:
            for met in metrics.keys():
                met_grf[qry_id][ref_id][met] = metrics[met]


def compute_organism_averages(met_grf, metrics, idchar, org_ids):
    """Compute average scores between and within each pair of organisms

    Args:
        bsr_graph: A NetworkX graph data structure containing a node for each
            sequence and with edges weighted using each BLAST-based metric
        metrics: An ordered list of metrics used in the met_grf data structure
        org_ids: A set containing each organism ID
        idchar: Character used to delineate between the organism ID and the
            remainder of the sequence ID
    Returns:
        org_avgs: A NetworkX graph data structure containing the total number
            of edges between each pair of organisms, the cumulative sum of each
            metric, and the average score for each metric (one node per
            organism, one edge per pair)
    """
    org_avgs = nx.Graph()

    for qry_id, ref_id, edata in met_grf.edges(data=True):
        qry_org = qry_id.split(idchar)[0]
        ref_org = ref_id.split(idchar)[0]

        if org_avgs.has_edge(qry_org, ref_org):
            org_avgs[qry_org][ref_org]['cnt'] += 1
            for met in metrics:
                org_avgs[qry_org][ref_org][met+'_sum'] += edata[met]
        else:
            org_avgs.add_edge(qry_org, ref_org, cnt=1)
            for met in metrics:
                org_avgs[qry_org][ref_org][met+'_sum'] = edata[met]
                org_avgs[qry_org][ref_org][met+'_avg'] = None

        # A new E-value minimum will need to be chosen after normaliztion
        if edata['evl'] == 181.:
            met_grf[qry_id][ref_id]['evl'] = None

    return org_avgs


def compute_global_averags(org_avgs, metrics):
    """Compute global averages for the entire graph

    Args:
        org_avgs: A NetworkX graph data structure with a node for each organism
            and edges containing the number of edges between each organism in
            the met_grf data structure, and the cumulative weight of all edges
            for each metric between each pair of organisms
        metrics: An ordered list of metrics used in the met_grf data structure
    Returns:
        Nothing, the org_avgs data structure is modified in place
    """
    # The 'global' node has degree 0
    org_avgs.add_node('global', cnt=0,
                      evl_sum=0., bit_sum=0., bpr_sum=0., bsr_sum=0.)

    for qry_org, ref_org, edata in org_avgs.edges(data=True):
        org_avgs.node['global']['cnt'] += edata['cnt']

        for met in metrics:
            org_avgs.node['global'][met+'_sum'] += edata[met+'_sum']
            temp_avg = edata[met+'_sum']/edata['cnt']
            org_avgs[qry_org][ref_org][met+'_avg'] = temp_avg

    glb_cnt = org_avgs.node['global']['cnt']

    for met in metrics:
        met_sum = org_avgs.node['global'][met+'_sum']  # float
        org_avgs.node['global'][met+'_avg'] = met_sum/glb_cnt


def normalize_bit_score_ratios(met_grf, metrics, idchar, org_avgs):
    """Convert Bit Scores into Bit Score Ratios

    Iterates through the edges in a NetworkX graph, dividing all
    cross-alignment scores by either the smaller or larger of the two
    self-alignment scores

    Convert Bit Scores into Bit Score Ratios and account for intra-/inter-
    organism differences, if requested
    """
    glb_avg = dict()

    for met in metrics:
        glb_avg[met] = org_avgs.node['global'][met+'_avg']

    min_scl = float("inf")  # Minimum scaling factor
    max_evl = float("-inf")  # Maximum observed -log10(E-value)

    for qry_id, ref_id, edata in met_grf.edges(data=True):
        qry_org = qry_id.split(idchar)[0]
        ref_org = ref_id.split(idchar)[0]

        for met in metrics:
            # Handle BLAST-rounded E-values separately
            if met == 'evl' and edata[met] is None:
                continue

            scale = glb_avg[met] / org_avgs[qry_org][ref_org][met+'_avg']
            met_grf[qry_id][ref_id][met] *= scale

            if met == 'evl':
                if scale < min_scl:
                    min_scl = scale
                if edata['evl'] > max_evl:
                    max_evl = edata['evl']

    # max_evalue + gap = zero_evalue * min_scale
    gap = 10
    min_zro_evl = max_evl + gap
    zro_evl = min_zro_evl / min_scl

    for qry_id, ref_id, edata in met_grf.edges(data=True):
        #if met_grf[qry_id][ref_id]['evl'] is None:
        if not met_grf[qry_id][ref_id]['evl']:
            qry_org = qry_id.split(idchar)[0]
            ref_org = ref_id.split(idchar)[0]
            scale = glb_avg[met] / org_avgs[qry_org][ref_org][met+'_avg']
            met_grf[qry_id][ref_id]['evl'] = zro_evl*scale


def print_abc_files(met_grf, out_pref):
    """Print MCL-formatted .abc graph files"""
    metrics = ['evl', 'bit', 'bpr', 'bsr']
    handle = dict()

    for met in metrics:
        handle[met] = open(out_pref+'_'+met+'.abc', 'w')

    for qry_id, ref_id, edata in met_grf.edges(data=metrics):
        if qry_id == ref_id:
            continue
        for met in metrics:
            out_line = '{0}\t{1}\t{2}\n'.format(qry_id, ref_id, edata[met])
            handle[met].write(out_line)

    for met in metrics:
        handle[met].close()


if __name__ == "__main__":
    sys.exit(main())
