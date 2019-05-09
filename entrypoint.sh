#!/bin/sh

if [ "$SIZE" = 'small' ]; then
    FILE="ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/phase3/data/HG00100/sequence_read/ERR013140.filt.fastq.gz"
elif [ "$SIZE" = "medium" ]; then
    FILE="ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/phase3/data/HG00100/sequence_read/SRR099966_1.filt.fastq.gz"
elif [ "$SIZE" = "large" ]; then
    FILE="ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/phase3/data/HG00100/alignment/HG00100.mapped.ILLUMINA.bwa.GBR.low_coverage.20130415.bam"
else
    echo "file size not set"
    exit 1
fi

test_file=$(date +"%Y-%m-%d_%H-%M-%S")
wget -O /volume/$test_file $FILE

sleep 3

python test.py /volume/$test_file /conf/config.yaml