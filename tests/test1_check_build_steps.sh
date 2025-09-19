#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
cd ..

tar -xvf tests/repositories/check_build_steps_git.tar -C /tmp
./rockbuilder.py --project ./tests/projects/check_build_steps.cfg
./rockbuilder.py --project ./tests/projects/check_build_steps.cfg --clean


result_file1="builddir/check_build_steps/build_steps.txt"
compare_file1="tests/resources/test1/build_steps.txt"

if cmp -s "$result_file1" "$compare_file1"; then
    echo "test1_1: OK"
    #echo "The contents of $result_file1 and $compare_file1 are identical."
else
    echo "test1_1: failed"
    echo "The contents of $result_file1 and $compare_file1 are different."
    exit 1
fi

result_file1="src_projects/check_build_steps/hello_world.txt"
compare_file1="tests/resources/test1/hello_world.txt"

if cmp -s "$result_file1" "$compare_file1"; then
    echo "test1_2: OK"
    #echo "The contents of $result_file1 and $compare_file1 are identical."
else
    echo "test1_2: failed"
    echo "The contents of $result_file1 and $compare_file1 are different."
    exit 1
fi
