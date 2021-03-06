#!/usr/bin/Rscript --vanilla --default-packages=utils

library(tools)
library(grDevices)
library(plyr)
library(ggplot2)
library(RColorBrewer)

# BlastGraphMetrics directory
# bgmdir <- "/Volumes/OdinsSaddlebag/Research/2014/clustering/BlastGraphMetrics"
bgmdir <- "../"

# Data sets
dss <- c("11111111111","11122222112","22222222222","22233333223","33333333333")

# Read in data
for (ds in dss) {
  fn <- paste("eck_",ds,"/shf_rnd/1e-5/nrm_dmnd/eck_",ds,"_shf_rnd_1e-5_nrm_dmnd_clusters_per_kog_summary.Rtab", sep="")
  tdf <- read.table(paste(bgmdir, fn, sep="/"), header=TRUE)
  tdf$DataSet <- as.factor(ds)
  if (exists("eck")) {
    eck <- rbind(eck, tdf)
  } else {
    eck <- tdf
  }
}

# Refactor the Metric columns to set the order
eck$Metric <- factor(eck$Metric,
                     levels=c("-Log10Evalue", "BitScore", "BitScoreRatio",
                              "AnchoredLength"))

eck <- ddply(eck, c("Metric", "Inflation"),
             transform, TotesClusters=sum(ClusterCount))

eck$Legend <- as.character(eck$ClustersPerKOG)
eck$Legend[as.numeric(eck$Legend) >= 5] <- "5+"
eck$Legend <- as.factor(eck$Legend)

# If you're lucky enough to not be red/green color blind, I think this color scheme looks better
# right <- "#006d2c"
# wrong <- brewer.pal(name="YlOrRd", n=7)[4:7]
right <- "#4575b4"
wrong <- rev(brewer.pal(name="RdYlBu", n=11))[7:10]

eck.reds <- nlevels(eck$Legend)-1
if (eck.reds > 0) {
  eck.clrs = c(right, wrong[1:nlevels(eck$Legend)-1])
} else {
  eck.clrs = c(right)
}

# Create ggplot object for Clusters per ECK statistics
eck.gg <- ggplot(data=eck,
                 aes(x=Inflation, weight=ClusterCount))
eck.gg <- eck.gg +geom_bar(aes(fill=Legend), binwidth=0.1)
eck.gg <- eck.gg +scale_fill_manual(
                      values=eck.clrs,
                      guide=guide_legend(
                                title="Clusters\nper ECK",
                                title.hjust=0.5))
eck.gg <- eck.gg +facet_grid(DataSet~Metric, scales="free", space="free")
eck.gg <- eck.gg +theme_bw()
eck.gg <- eck.gg +ggtitle("Sensitivity")
eck.gg <- eck.gg +ylab("ECK Count")
eck.gg <- eck.gg +xlab("MCL Inflation Parameter")
eck.gg <- eck.gg +geom_hline(yintercept=seq(100,max(eck$ClusterCount),100),
                             color="lightgray", size=0.05)

# Plot barcharts to PDFs
pdf("eckFragmentationShuffledRandomSensitivity.pdf", width=8.5, height=9)
eck.gg
dev.off()
