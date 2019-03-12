#!/bin/sh
wget -O test_file ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/phase3/data/HG00100/sequence_read/ERR013140.filt.fastq.gz

sleep 3

python test.py test_file /conf/config.yaml