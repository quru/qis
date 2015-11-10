#
# Quru Image Server
#
# Document:      bench.py
# Date started:  26 May 2015
# By:            Matt Fozard
# Purpose:       Repeatable load testing / benchmarking tool
# Requires:
# Copyright:     Quru Ltd (www.quru.com)
# Licence:
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see http://www.gnu.org/licenses/
#
# Last Changed:  $Date$ $Rev$ by $Author$
#
# Notable modifications:
# Date       By    Details
# =========  ====  ============================================================
#
#
# Note: this script stands alone and can be run from anywhere that has Python
#

import urllib2
import os
import sys
import time

from multiprocessing.pool import Pool, ThreadPool


_PoolType = Pool  # or ThreadPool
_vb = False

RETURN_OK = 0
RETURN_MISSING_PARAMS = 1
RETURN_BAD_PARAMS = 2

REFERRER = 'qis/benchmark'

# Sample URLs, based on a production workload, changed to use test images
URLS = [
    'image?src=test_images/cowboy.jpg&width=150',
    'image?src=test_images/bear.jpg&width=640&height=480&halign=l0&valign=t0&autosizefit=1',
    'image?src=test_images/sunrise1.jpg&fill=FFFFFF&height=480&width=640',
    'image?src=test_images/sunrise2.jpg&top=0.055084745762&left=0.170000000000&bottom=0.817815678442&right=0.970000000000&height=480&width=640',
    'image?src=test_images/bear.jpg&width=150',
    'image?src=test_images/sunrise1.jpg&fill=FFFFFF&bottom=0.999999999999&height=480&width=640',
    'image?src=test_images/cowboy.jpg&width=640&height=480&halign=l0&valign=t0&autosizefit=1',
    'image?src=test_images/bear.jpg&fill=FFFFFF&height=480&width=640',
    'image?src=test_images/sunrise2.jpg&top=0.084677419354&bottom=0.991958165889&height=480&width=640',
    'original?src=test_images/quru110.png&stats=0',
    'image?src=test_images/sunrise1.jpg&width=150',
    'api/v1/details?src=test_images/quru470.png',
    'image?src=test_images/bear.jpg&tmp=SmallJpeg&width=200&quality=100&format=jpeg',
    'image?src=test_images/quru470.png&width=150',
    'image?src=test_images/pdftest.pdf&width=200',
    'image?src=test_images/sunrise2.jpg&right=0.523050000000&width=200',
    'image?src=test_images/pdftest.pdf&width=640',
    'image?src=test_images/dorset.jpg&width=150',
    'image?src=test_images/cathedral.jpg&width=200',
    'image?src=test_images/cowboy.jpg&left=0.280000000000&right=0.808333333333&width=200',
    'image?src=test_images/sunrise1.jpg&top=0.0870&left=0.0000&bottom=0.8333&right=1.0000&height=480&width=640',
    'image?src=test_images/pdftest.pdf&width=200&height=200&fill=BBBBBB',
    'image?src=test_images/cowboy.jpg&tmp=SmallJpeg&width=200&quality=100&format=jpeg',
    'image?src=test_images/cathedral.jpg&top=0.019920318725&left=0.130000000000&bottom=0.976095617529&right=0.764000000000&width=200',
    'image?src=test_images/bear.jpg&width=308',
    'image?src=test_images/sunrise2.jpg&width=640&height=480&halign=l0&valign=t0&autosizefit=1',
    'image?src=test_images/bear.jpg&fill=FFFFFF&bottom=0.810810810810&height=480&width=960',
    'image?src=test_images/cathedral.jpg&width=308',
    'image?src=test_images/dorset.jpg&width=308',
    'image?src=test_images/thames.jpg&width=308',
    'image?src=test_images/multipage.tif&left=0.046666666666&right=0.709725000000&width=200',
    'original?src=test_images/quru470.png',
    'image?src=test_images/sunrise2.jpg&fill=FFFFFF&top=0.060000000000&bottom=0.420000000000&height=480&width=960',
    'image?src=test_images/thames.jpg&fill=FFFFFF&top=0.276666666666&bottom=0.886681917047&height=480&width=640',
    'image?src=test_images/cowboy.jpg&fill=FFFFFF&top=0.010000000000&bottom=0.607514937873&right=0.999999999999&height=480&width=640',
    'api/v1/details?src=test_images/sunrise1.jpg',
    'image?src=test_images/sunrise1.jpg&height=305&width=232&fill=ffffff',
    'image?src=test_images/sunrise2.jpg&height=305&width=232&fill=ffffff',
    'image?src=test_images/bear.jpg&width=568&height=700&autosizefit=0&strip=1&format=jpg&fill=none&stats=0',
    'image?src=test_images/cowboy.jpg&width=2816&height=2112&strip=1&format=jpg&fill=none&autosizefit=0&stats=0&tile=8:16',
    'image?src=test_images/cowboy.jpg&width=2816&height=2112&strip=1&format=jpg&fill=none&autosizefit=0&stats=0&tile=12:16'
]

# Roughly how many different images are in the image URLs
URL_IMAGES = 8


def validate_params(server_url, num_requests, cache_pct, num_clients):
    """
    Validates the command line parameters, returning 0 on success or a code
    number that can be used as the application return value on error.
    """
    # Validate server_url
    log('Checking connectivity to %s' % server_url)
    try:
        req = urllib2.Request(server_url)
        req.add_header('Referer', REFERRER)
        urllib2.urlopen(req)
    except urllib2.URLError as e:
        error('Failed to connect to %s: %s' % (server_url, str(e)))
        return RETURN_BAD_PARAMS

    # Validate the rest
    if num_requests < 1:
        error('Number of requests cannot be below 1')
        return RETURN_BAD_PARAMS
    if cache_pct < 0 or cache_pct > 100:
        error('Percent from cache must be between 0 and 100')
        return RETURN_BAD_PARAMS
    if num_clients < 1 or num_clients > 100:
        error('Number of clients must be between 1 and 100')
        return RETURN_BAD_PARAMS

    return RETURN_OK


def log(astr):
    """
    Outputs an informational message.
    """
    print 'LOG   ' + str(os.getpid()) + ' - ' + astr


def error(astr):
    """
    Outputs an error message.
    """
    print 'ERROR ' + str(os.getpid()) + ' - ' + astr


def show_usage():
    """
    Outputs usage information.
    """
    print '\nRuns a benchmarking test against an image server by requesting a series'
    print 'of sample image URLs. The test can be tuned by adjusting the number of'
    print 'image requests, the number of simultaneous requests, and the percentage of'
    print 'requests to return from cache. Repeating the test with the same parameters'
    print 'will generate the same set of requests so that timings can be compared.'
    print '\nUsage:'
    print '       python bench.py [options] server_url [num_requests] ' \
          '[cache_percent] [num_clients]'
    print '\nWhere:'
    print '       server_url is e.g. http://images.example.com/'
    print '       num_requests is the number of server requests to make, default 1000'
    print '       cache_percent is the percentage of images to return from cache, default 90'
    print '       num_clients is the number of simultaneous requests to make, default 4'
    print '\nOptions:'
    print '       --verbose to output more detailed status logs'
    print '       --only-warm to only warm the cache then skip the actual tests'
    print '       --skip-warm to skip the cache warming and run the tests immediately'
    print '\nExamples:'
    print '       python bench.py http://images.example.com/'
    print '       python bench.py --verbose http://images.example.com/ 5000 80 10'
    print '\nNotes:'
    print 'Set cache_percent to 0 to re-generate every image every time. This is very'
    print 'CPU intensive on the image server and tests performance under load. Set '
    print 'cache_percent to 100 to serve every image from cache where possible*. This '
    print 'tests the level of throughput under ideal conditions. The default value of '
    print '90 represents a typical workload.'
    print '\n* The tests also include some URLs that are never returned from cache.\n'


def get_parameters():
    """
    Returns a tuple of 7 items for the parameters provided on the command line:
    server_url, num_requests, from_cache_pct, num_clients, verbose, warm_only, skip_warm
    """
    server_url = None
    num_requests = None
    from_cache_pct = None
    num_clients = None
    verbose = False
    warm_only = False
    skip_warm = False

    for arg in sys.argv:
        if arg == __file__:
            pass
        elif arg == '--verbose':
            verbose = True
        elif arg == '--only-warm':
            warm_only = True
        elif arg == '--skip-warm':
            skip_warm = True
        elif server_url is None:
            server_url = arg
        elif num_requests is None:
            num_requests = int(arg)
        elif from_cache_pct is None:
            from_cache_pct = int(arg)
        elif num_clients is None:
            num_clients = int(arg)

    if server_url and not server_url.endswith('/'):
        server_url += '/'

    # Apply defaults if no parameter given
    if num_requests is None:
        num_requests = 1000
    if from_cache_pct is None:
        from_cache_pct = 90
    if num_clients is None:
        num_clients = 4

    return server_url, num_requests, from_cache_pct, num_clients, \
        verbose, warm_only, skip_warm


def single_request(url):
    """
    Requests a single image and returns a tuple of the HTTP status code,
    from-cache flag (as a string or None), and time taken in seconds.
    """
    req = urllib2.Request(url)
    req.add_header('Referer', REFERRER)
    status = 0
    from_cache = None
    start_time = time.time()
    try:
        handler = urllib2.urlopen(req)
        status = handler.getcode()
        if status == 200:
            from_cache = handler.info().get('X-From-Cache')
    except urllib2.HTTPError as e:
        error(str(e))
        status = e.code
    except Exception as e:
        error(str(e))
        status = 0
    end_time = time.time()
    if _vb:
        fc_flag = 'Cache' if from_cache == 'True' else \
                  'Gen  ' if from_cache == 'False' else \
                  '-    '
        log('%d %s %s' % (status, fc_flag, url))
    return status, from_cache, (end_time - start_time)


def make_requests(server_url, num_requests, cache_pct, num_clients,
                  verbose, warm_only, skip_warm):
    """
    Runs the benchmarking tests and prints the results.
    """
    global _vb
    _vb = verbose

    # Create a URL list of num_requests
    loops = num_requests / len(URLS)
    plus = num_requests % len(URLS)
    url_list = (URLS * loops) + URLS[:plus]

    # Add an occasional recache=1 to simulate the uncached image requests.
    # Because the same images are repeated in URLS, doing a recache on one
    # will end up recaching the others for that same image.
    # We therefore need to reduce the actual number of recaches by rc_factor.
    if cache_pct != 0 and cache_pct != 100:
        rc_factor = len(URLS) / float(URL_IMAGES)
        num_recaches = num_requests * ((1 - (cache_pct / 100.0)) / rc_factor)
        recache_every = int(round(num_requests / num_recaches))

    log('Building request list')
    for idx, image_url in enumerate(url_list):
        # Prepend server to image URL
        url_list[idx] = server_url + image_url

        if cache_pct == 0:
            # Don't cache anything
            url_list[idx] += '&cache=0'
        elif cache_pct != 100:
            # Uncache occasionally
            if idx % recache_every == 0:
                url_list[idx] += '&recache=1'
        else:
            # Cache everything
            pass

    if not skip_warm:
        if cache_pct != 0:
            log('Pre-warming the image cache')
            for image_url in URLS:
                try:
                    url = server_url + image_url
                    req = urllib2.Request(url)
                    req.add_header('Referer', REFERRER)
                    urllib2.urlopen(req)
                    if verbose:
                        log('OK for ' + url)
                except urllib2.URLError as e:
                    error('Error %s for %s, cannot run tests' % (str(e), url))
                    raise Exception('Failed to initialise the tests')
        else:
            log('NOTE! You need to manually clear your image cache if you have '
                'previously run these tests.')
    else:
        log('Cache pre-warming skipped')

    if warm_only:
        log('Tests skipped')
        return RETURN_OK

    # Run the tests
    log('Creating clients, running tests')
    pool = _PoolType(num_clients)
    start_time = time.time()
    results = pool.map(single_request, url_list)
    pool.close()
    pool.join()
    end_time = time.time()
    log('Complete')

    # Compile the results
    total_time = end_time - start_time
    err_count = 0
    ok_count = 0
    ok_time_total = 0
    cached_count = 0
    cached_time_total = 0
    cached_time_worst = 0
    gen_count = 0
    gen_time_total = 0
    gen_time_worst = 0
    for status, from_cache, wait_time in results:
        if status == 200:
            ok_count += 1
            ok_time_total += wait_time
            if from_cache == 'True':
                cached_count += 1
                cached_time_total += wait_time
                if wait_time > cached_time_worst:
                    cached_time_worst = wait_time
            else:
                gen_count += 1
                gen_time_total += wait_time
                if wait_time > gen_time_worst:
                    gen_time_worst = wait_time
        else:
            err_count += 1

    print '\nResults'
    print '======='
    print '%d successful requests, %d errors.' % (
        ok_count, err_count
    )
    print 'Run time %f seconds = %f requests/sec.\n' % (
        total_time, ok_count / total_time
    )
    if ok_count != 0:
        print 'Average response %f seconds' % (ok_time_total / ok_count)
        if gen_count != 0:
            print '  * %d non-cached, average response %f seconds, worst %f seconds' % (
                gen_count, gen_time_total / gen_count, gen_time_worst
            )
        else:
            print '  * 0 non-cached responses'
        if cached_count != 0:
            print '  * %d from cache, average response %f seconds, worst %f seconds' % (
                cached_count, cached_time_total / cached_count, cached_time_worst
            )
        else:
            print '  * 0 from cache'
    print ''

    return RETURN_OK


if __name__ == '__main__':
    try:
        # Get params
        server_url, num_requests, cache_pct, num_clients, \
            verbose, warm_only, skip_warm = get_parameters()
        if not server_url:
            show_usage()
            exit(RETURN_MISSING_PARAMS)

        rc = validate_params(server_url, num_requests, cache_pct, num_clients)
        if rc != RETURN_OK:
            exit(rc)

        rc = make_requests(
            server_url, num_requests, cache_pct, num_clients,
            verbose, warm_only, skip_warm
        )
        exit(rc)

    except Exception as e:
        print 'Utility exited with error:\n' + str(e)
        raise
