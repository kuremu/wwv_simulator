#!/bin/bash

test_date() {
    printf "$1 $2\n\x1b[32m"
    python wwv_simulator.py --date $1 --time $2 --period 00:01:00 --station wwv test.wav
    python wwv_decoder.py test.wav
    printf "\x1b[m"
}

# (20)16, 366th, 11:30, leap_second, DUT1 -0.3
test_date 31/12/16 11:30:00
test_date 01/01/17 02:30:00

# AEDT->AEST transition
test_date 01/04/22 00:00:00
test_date 02/04/22 00:00:00
test_date 03/04/22 00:00:00
