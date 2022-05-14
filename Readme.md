# wwv_simulator

*A simulation of the WWV/WWVH stations, including time code and announcements.*

**Usage**  

`python wwv_simulator.py
        [-h] [--station [{wwv,wwvh}]] [--date [DATE_STR]]
        [--time [TIME_STR]] [--period [PERIOD]] [--clock]
        [output]`


        -h, --help             show this help message and exit
        --station [{wwv,wwvh}] station (WWV/WWVH)
        --date [DATE_STR]      custom start date (d/m/y)
        --time [TIME_STR]      custom start time (H:M:S)
        --period [PERIOD]      output given duration of audio and exit (H:M:S)
        --clock                output broadcast time to stderr
        output                 output destination appended to sox. a value of
                               '-' writes 1ch 44.1k 16-bit signed-integer
                               samples to stdout.

**Dependencies**  

    python 3 (tested with 3.9.12)  
    sox (tested with v14.4.2)  
    espeak (tested with v1.48.15)  

Tested on Debian, OS X, Cygwin64 for Windows.

## About the program

`wwv_simulator` plays a simulation of the WWV and WWVH time broadcasts. It uses
SoX to produce the various tones heard in the broadcasts and to play the
result, and espeak to speak the announcements.

WWV is located in Fort Collins, Colorado and WWVH is located in Kekaha, Hawaii.
They transmit on 5, 10, 15 and 20 MHz and can be heard quite broadly around the
world, depending on the time of day and ionospheric conditions. They transmit
tones, second pulses, various announcements and a 100 Hz time code that can be
used to set radio-controlled clocks.

`wwv_simulator` recreates most of the features of these broadcasts, including
leap seconds and DUT1 values, and downloads historical data in order to
simulate what the stations would have been broadcasting in the past. WWV/WWVH
differ slightly, most notably in the voices which are male for WWV and female
for WWVH. Use the `--station` argument to select between WWV/WWVH (default
WWV).

Running `wwv_simulator` without any arguments will give you a "live" broadcast,
tracking the current time. You can also set a custom `--date` and `--time` in
order to eg. hear what happens during a leap second, although note this will
only work if `wwv_simulator` has already run long enough for the historical
data file[^4] to have completely downloaded:

        python wwv_simulator.py --date 31/12/16 --time 23:59:00

The audio is normally output second by second, but if you want to quickly
output a duration use the `--period` argument along with an appropriate output
argument:

        python wwv_simulator.py --date 31/12/99 --time 23:59:00 --period 00:02:00 wwv_nye_99.wav
        
You can analyse the BCD time code in the resulting file with wwv_decoder.py[^6]
(see below):

        python wwv_decoder.py wwv_nye_99.wav 0 60  
        
        python wwv_decoder.py wwv_nye_99.wav 60 120
        
The `--clock` argument will print an updating clock to stderr.

If you are used to hearing both broadcasts at once, starting two different
instances should play at almost precisely the same time. Using raw output we
can chain with SoX to lower volume for the more distant station:

        python wwv_simulator.py --station wwvh  
        
        python wwv_simulator.py - | sox -t raw -r44.1k -es -b16 - -d vol 0.25  

## About the broadcast/simulation

### Second pulses
These are 5 millisecond bursts of 1200 Hz and occur every second during the
broadcast apart from seconds 29, 59 and 0 (when the minute/hour tone occurs).
All other components of the broadcast are silenced for the duration of the
second pulses.

### DUT1 correction pulses
DUT1 (see below) is encoded in the first 16 second pulses (seconds 1 to 17). A
sequence of second pulses can include doubled pulses, each double pulse
accounting for 0.1 seconds worth of the DUT1 value (for example if there are 3
doubled ticks the DUT1 value is 0.3). If these doubled ticks occur in the first
8 seconds of this period, the DUT1 value is positive; if they occur in the last
8 seconds, the DUT1 value is negative.

### Standard frequencies
Tones play through the first 45 seconds of most minutes, alternating between
500 Hz and 600 Hz, with a 440 Hz tone on minute 2 on WWV and minute 1 on WWVH.
The 440 Hz tone is omitted during the first hour of each day. The tone stops at
second 45 to allow for the time announcement. Some minutes have the tone
completely silenced: this is to allow for occasional announcements which can
span seconds 1 to 45, including announcements occurring on the *other*
station's broadcast. This is to account for situations where both broadcasts
can be heard from the same location.

### BCD time code
A Binary Coded Decimal time code on a 100 Hz subcarrier. The time code consists
of a pulse every second from second 1 onwards: short pulses indicate 0, long
pulses indicate 1 and longer "marker" pulses for synchronisation purposes every
10th second. The time code includes the current hour, minute, day of the year,
last two digits of the year, DUT1 value (including sign), leap second warning
and two daylight savings flags. The leap second warning occurs for the entire
month which is scheduled to end with a leap second. The primary DST flag is set
on the UTC day on which daylight savings time starts locally and the secondary
is set on the following day. The DST flags are unset in the same manner when
daylight savings ends. For more information on the BCD time code look at the
NIST page on the WWV/WWVH broadcasts[^1] and for even finer detail check the
appendices of the NIST Time and Frequency Services guide[^2].

## Announcements

In the real WWV/WWVH transmissions, the announcements are often made using
human voices, although some of the more recent ones appear to be TTS. Time
announcements are made every minute and other announcements occur in the first
45 seconds. WWV and WWVH use different voices for their time announcements and
station ID to distinguish themselves from each other: WWV uses broadcaster John
Doyle and WWVH uses Jane Barbe, who is well known for her voice work as the
"AT&T Lady". WWV generally makes its announcements in the first 20 minutes of
the hour and WWVH in the last 20. The content of the announcements are mostly
identical.

### Time announcement
The time of day is announced every minute from second 45. WWVH's announcement
comes first at about 45 seconds and WWV's announcement is at about 52 seconds.
This is in case both broadcasts can be heard at once from the same location.

### Geophysical alerts
*[WWV 18:00 WWVH 45:00]*  
Messages from NOAA that provide information about solar terrestrial conditions.
The content of the announcement is pulled from the NOAA website[^3].

### Ionospheric experiments
*[WWV 08:00 WWVH 48:00]*  
Starting in 2021 WWV/WWVH started hourly ionospheric experiments. These consist
of chirps and sweeps like you might hear out of high frequency over-the-horizon
Radar systems. The audio generated in wwv_simualator is my attempt to recreate
the experiment as heard during April 2022.

### Station ID
*[WWV 00:00, 00:30 WWVH 00:29, 00:59]*  
Information about the transmitting station and the transmission itself read by
the station's main announcer.

### MARS / Hacker News announcements
*[WWV 10:00 WWVH 50:00]*  
Announcements of Military Auxiliary Radio System exercises. MARS is "an
organization established by DoD that trains volunteer Amateur Radio operators
to provide contingency high-frequency (HF) radio communications assistance in
times of natural disasters and other urgent situations"[^1]. Since these
announcements are completely unpredictable, `wwv_simulator` announces the
titles of the current top posts on Hacker News[^5] instead.

## Notes

### DUT1
DUT1 is the difference between UTC and UT1. UT1 is Earth's "true" time based on
its rotation which is gradually slowing, and is determined by astronomical
observation. UT1 is useful for some people and so DUT1 is encoded in both the
BCD time code and the second pulses of the broadcast with 0.1 second precision.

### Leap seconds
Leap seconds are manually added into UTC in order that DUT1 never surpasses
-0.9s, keeping UTC and UT1 within a second of each other. Consequently, DUT1
changes when a leap second is added. Scheduling of leap seconds is delegated to
the International Earth Rotation and Reference Systems Service (IERS). Leap
seconds are always scheduled for the last day of June or December.

### Daylight savings
The BCD time code includes flags that indicate whether daylight savings is in
effect. In the real-world WWV and WWVH brocasts, they are used to indicate
daylight savings time for the US, while `wwv_simulator` uses these bits to
indicate daylight savings time in the user's local timezone. Working out DST
accurately is a convoluted process, and since it isn't a very important part of
the broadcast we're just comparing information from Python's standard timezone
functions against a list of DST timezone abbreviations.

### Sources
`wwv_simulator` downloads a large (roughly 3.5 MB) history of DUT1 values[^4],
starting from 1973 and with predictions up to about a year into the future.
Using the DUT1 values we can also determine when leap seconds occurred. This is
the only material we use to determine leap seconds. DUT1 values and leap
seconds are announced in advance by the IERS and are based on predictions, so
the official day of future changes might be different from the day they occur
in `wwv_simulator`.

### Testing the BCD time code with wwv_decoder.py
Included is a slightly modified version of wwv_decoder.py by vsergeev[^6]. You
can use test.sh to have a look at the decoded time code for different dates.
wwv_decoder.py depends on numpy and scipy.

[^1]: https://www.nist.gov/time-distribution/radio-station-wwv/wwv-and-wwvh-digital-time-code-and-broadcast-format  
[^2]: https://www.govinfo.gov/content/pkg/GOVPUB-C13-fec48b1a26ef48315cd2468325bf2bd7/pdf/GOVPUB-C13-fec48b1a26ef48315cd2468325bf2bd7.pdf  
[^3]: https://services.swpc.noaa.gov/text/wwv.txt  
[^4]: https://datacenter.iers.org/data/latestVersion/9_FINALS.ALL_IAU2000_V2013_019.txt  
[^5]: https://news.ycombinator.com/  
[^6]: https://github.com/vsergeev/radio-decoders/  
