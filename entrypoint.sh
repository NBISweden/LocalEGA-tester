#!/bin/sh
wget -O test_file ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/phase3/data/HG00458/alignment/HG00458.unmapped.ILLUMINA.bwa.CHS.low_coverage.20130415.bam

sleep 3

python test.py test_file /conf/config.yaml