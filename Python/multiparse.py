#!/usr/bin/env python

__author__ = "Liam Fearnley (@lfearnley)"

import glob
import gzip
import multiprocessing
import os
import shutil
import sys
from collections import defaultdict
from multiprocessing.pool import Pool
from pathlib import Path

def create_output_dir(path_list, clobber):
    for path in path_list:
        if os.path.exists(path):
            if not clobber:
                print("ERROR: An output file path exists at " + path)
                print("Exiting - re-run with the --clobber flag to ignore existing "
                      "files")
                import sys
                sys.exit(-1)
            else:
                shutil.rmtree(path)
                os.makedirs(path)
        else:
            os.makedirs(path)


def read_perread_file(queue, read_summary_path):
    path = Path(read_summary_path)
    experiment_id = path.parent.name
    max_length = 0
    collation_dict = {}
    done_set = set()
    total_count = 0
    successful_run = False
    try:
        for line in gzip.open(read_summary_path, 'rt'):
            split_line = line.strip().split("\t")
            if "Total" in line:
                total_count = float(line.replace("Total", "").strip())
                continue
            if len(split_line) <= 1:
                continue
            if line.count("@@SRR") > 1:
                print("TICK!" + read_summary_path + "\t" + line)
            for i in range(1, len(split_line)):
                str_tuple = split_line[i].split(":")
                if len(str_tuple) < 5:
                    print("ERROR - truncated tuple, abandoning file")
                    print(read_summary_path)
                    print(str_tuple)
                    print(line)
                    queue.put((experiment_id, 0, collation_dict))
                    return
                else:
                    if str_tuple[0] not in collation_dict:
                        collation_dict[str_tuple[0]] = defaultdict(int)
                    collation_dict[str_tuple[0]][str_tuple[1]] += 1
                    max_length = max(max_length, int(str_tuple[4]))
        successful_run = True
    except EOFError as ex:
        print("Note: ", read_summary_path, " has a malformed end-of-file." )
    if total_count == 0 or not successful_run:
        # print("ERROR " + read_summary_path)
        queue.put((experiment_id, 0, {}))
        return
    else:
        print(read_summary_path + "\t" + str(total_count))
        for key in collation_dict:
            for idx in collation_dict[key]:
                collation_dict[key][idx] = 1.0*(collation_dict[key][idx])/total_count
    queue.put((read_summary_path, max_length, collation_dict))
    return

def write_file(queue, motif_csv_out_path, sample_csv_out_path, manifest_path):
    seen_motifs = set()
    group_dict = {}
    name_dict = {}
    with open(manifest_path, 'rt') as manifest_file:
        for line in manifest_file:
            if line.strip() == "":
                continue
            spline = line.strip().split()
            if len(spline) < 4:
                print("Fail to read manifest on line: ")
                print(line)
            group_dict[spline[0]] = spline[3]
            name_dict[spline[2]] = spline[0]
    while True:
        case = queue.get()
        # print("Printcase: " + case[0] + "\t" + str(case[1]) + "\tdictlen: " + str(len(case[2])))
        if case == "DONE":
            queue.task_done()
            break
        experiment_path = case[0]
        experiment_id = name_dict[experiment_path]
        max_len = int(case[1])
        collation_dict = case[2]
        group = group_dict[experiment_id]
        if max_len == 0:
            print("ERROR: Sample parse error - Skipping exp " + experiment_id)
            continue
        output_list = []
        length_dict = defaultdict(int)
        min_length = 1000
        max_length = -1000
        # Fix this up.
        with open(sample_csv_out_path + experiment_id + ".csv", 'wt') as sample_file_handle:
            sample_file_handle.write("motif,mlen")
            for i in range(1, max_len+1):
                sample_file_handle.write(","+str(i))
            sample_file_handle.write("\n")
            for key in collation_dict:
                key_len = str(len(key))
                sample_file_handle.write(key +"," +str(len(key.strip())))
                folder_root = motif_csv_out_path+key_len+"mers/"
                if not os.path.exists(folder_root):
                    os.makedirs(folder_root)
                with open(folder_root + key + ".csv", 'at') as csv_file_handle:
                    if key not in seen_motifs:
                        csv_file_handle.write("sample,motif,mlen,rlen,grp")
                        for i in range(1, max_len + 1):
                            csv_file_handle.write("," + str(i))
                        csv_file_handle.write("\n")
                        seen_motifs.add(key)
                    csv_file_handle.write(experiment_id + "," + key + ","
                                          + str(len(key)) + "," + str(max_len) +","+group)
                    key_dict = collation_dict[key]
                    for count_idx in range(1, max_len+1):
                        key_idx = str(count_idx)
                        if key_idx in key_dict:
                            csv_file_handle.write("," + str(key_dict[key_idx]))
                            sample_file_handle.write(","+str(key_dict[key_idx]))
                        else:
                            csv_file_handle.write(",")
                            sample_file_handle.write(",")
                    csv_file_handle.write("\n")
                    sample_file_handle.write("\n")
                    min_length = min(min_length, len(key))
        queue.task_done()
    return

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    mode_group = parser.add_argument_group(title="Mode options")
    mode_group.add_argument("-S", "--summarise", action="store_true",
                            dest="summarise", help="Summarise superSTR runs "
                                                   "into motif files.")
    mode_group.add_argument("-p", "--plot", action="store_true",
                            dest="plot_motif", help="Plot motif plots.")
    mode_group.add_argument("-s", "--sample_plot", action="store_true",
                            dest="plot_sample", help="Plot per-sample plots.")
    paths_group = parser.add_argument_group(title="File paths")
    paths_group.add_argument("--input", action="store", dest="input_path",
                        help="Input path; should be a directory containing "
                             "one or more superSTR runs.")
    paths_group.add_argument("-m", "--manifest", dest="manifest_path", default=None,
                             help="Manifest path")
    paths_group.add_argument("--output", action="store", dest="output_path",
                        help="Output path for files.")
    optional_arguments = parser.add_argument_group(title="Optional arguments")
    optional_arguments.add_argument("--clobber", action="store_true",
                                    dest="clobber", default=False,
                                    help="Clobber existing files.")
    optional_arguments.add_argument("-r", "--readlength", action="store",
                                    dest="read_length", default=150,
                                    help="Manually set read length (default 150nt).")
    optional_arguments.add_argument("-@", "--threads", action="store",
                            dest="threadcount", default=4,
                            help="Number of threads for multiparser execution"
                                 " (default=4)")
    # Default to help message if no arguments provided.
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    # Parse arguments - TODO: error handling.
    args = parser.parse_args()
    # Set up paths
    thread_count = int(args.threadcount)
    root_path = os.path.abspath(args.input_path)
    output_root_path = os.path.abspath(args.output_path)
    motif_csv_out_path = output_root_path + "/motifs/"
    sample_csv_out_path = output_root_path + "/samples/"
    manifest_path = os.path.abspath(args.manifest_path)
    # Create/clobber output directories as required.
    create_output_dir([motif_csv_out_path,sample_csv_out_path], args.clobber)
    # Processing: if summarise flag set, input should be processed first.
    if args.summarise:
        pool = Pool(thread_count)
        m = multiprocessing.Manager()
        queue = m.JoinableQueue(maxsize=100)
        if manifest_path:
            filelist = []
            with open(manifest_path, 'rt') as manifest_file:
                for line in manifest_file:
                    if line.strip() == "":
                        continue
                    spline = line.strip().split()
                    filelist.append(spline[2])
        else:
            filelist = glob.glob(root_path + "*/per_read.txt.gz")
        p = multiprocessing.Process(target=write_file, args=(queue, motif_csv_out_path, sample_csv_out_path, manifest_path))
        p.start()
        # split filelist in 10 pieces:
        inputargs = [(queue, os.path.abspath(file)) for file in filelist]
        pool.starmap(read_perread_file, inputargs)
        pool.close()
        pool.join()
        queue.put("DONE")
        p.join()
        print("Runthrough")
    if args.plot_motif:
        # Check that input directory contains at least one summarised CSV
        pass
    if args.plot_sample:
        # Check that input directory contains at least one summarised CSV
        pass