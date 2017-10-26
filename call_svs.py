#!/usr/bin/env python

import sys
import argparse
import os
import errno
import os.path

import subprocess

from pipeinspector.build38analysisdirectory import AnalysisDirectory, AnalysisSvDirectory
from pipeinspector.models import Base, ComputeWorkflowSample

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check analysis directory for completeness', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('database', metavar='<FILE>', help='sqlite database of samples')
    parser.add_argument('workorder', metavar='<INT>', nargs='+', help='work order id to process')
    args = parser.parse_args()
    db_url = 'sqlite:///' + args.database
    db = create_engine(db_url)
    Base.metadata.create_all(db)
    Session = sessionmaker(bind=db)

    for workorder in args.workorder:
        session = Session()
        for sample in session.query(ComputeWorkflowSample).filter(
                        ComputeWorkflowSample.source_work_order == workorder
                        ):
            if (sample.analysis_cram_verifyed and sample.analysis_sv_verified != True):
                if sample.analysis_sv_path is None:
                    sample.analysis_sv_path = os.path.join(sample.analysis_cram_path, 'sv')
                directory = AnalysisDirectory(sample.analysis_gvcf_path)
                cram_file = directory.output_file_dict['*.cram'][0]
                filename = os.path.basename(cram_file)
                sample_name = filename.split('.cram')[0]

                sv_directory = AnalysisSvDirectory(sample.analysis_sv_path)
                complete = True
                if not sv_directory.staging_complete():
                    # stage directory
                    try:
                        os.makedirs(sample.analysis_sv_path)
                    except OSError as e:
                        if e.errno != errno.EEXIST:
                            raise
                    try:
                        os.symlink(cram_file, os.path.join(sample.analysis_sv_path, filename))
                    except OSError as e:
                        if e.errno != errno.EEXIST:
                            raise
                    try:
                        os.symlink(cram_file + '.crai', os.path.join(sample.analysis_sv_path, filename + '.crai'))
                    except OSError as e:
                        if e.errno != errno.EEXIST:
                            raise
                os.chdir(sample.analysis_sv_path)
                if not sv_directory.cnvnator_complete():
                    # launch cnvnator
                    complete = False
                    print subprocess.check_output(['bash', '/gscuser/dlarson/src/internal-sv-pipeline/cnvnator_histogram.sh', filename])
                if not sv_directory.extract_complete():
                    # launch
                    complete = False
                    print subprocess.check_output(['bash', '/gscuser/dlarson/src/internal-sv-pipeline/extract_sv_reads.sh', filename])
                elif not sv_directory.lumpy_complete():
                    # launch
                    complete = False
                    subprocess.call(['bash', '/gscuser/dlarson/src/internal-sv-pipeline/lumpy.sh', filename])
                elif not sv_directory.svtyper_complete():
                    complete = False
                    subprocess.call(['bash', '/gscuser/dlarson/src/internal-sv-pipeline/genotype.sh', filename])
                sample.analysis_sv_verified = complete
                session.commit()
                if complete:
                    sys.stderr.write("{0} complete\n".format(sample_name))
        session.close()
