"""
validity_test_spikes.py

Suite of tests to assess "face validity" of spiking data analysis functions in spikes.py
Usually used to test new or majorly updated functions to ensure they perform as expected.

Includes tests that parametrically estimate spike rate as a function of the simulated data mean,
number of trials, etc. to establish methods produce expected pattern of results.

Plots results and runs assertions that basic expected results are reproduced

FUNCTIONS
test_rate           Tests of spike rate estimation functions

test_rate_stats     Tests of spike rate statistic estimation functions
rate_stat_test_battery  Runs standard battery of tests of rate stat functions

test_isi_stats      Tests of inter-spike interval statistic estimation functions
isi_stat_test_battery  Runs standard battery of tests of ISI stat functions
"""
# TODO  Generalize testing framework of test_rate cf other validity test functions
#       (test battery function, n_trials test)
import os
import time
from warnings import warn
from math import sqrt
import numpy as np
import matplotlib.pyplot as plt

from spynal.tests.data_fixtures import simulate_dataset
from spynal.spikes import simulate_spike_trains, times_to_bool, \
                                   rate_stats, isi, isi_stats, \
                                   plot_mean_waveforms, plot_waveform_heatmap
from spynal.spectra import compute_tapers


# =============================================================================
# Tests for rate computation functions
# =============================================================================
def test_rate(method, rates=(5,10,20,40), data_type='timestamp', n_trials=1000,
              do_tests=True, do_plots=False, plot_dir=None, seed=1, **kwargs):
    """
    Basic testing for functions estimating spike rate over time.

    Generates synthetic spike train data with given underlying rates,
    estimates rate using given function, and compares estimated to expected.

    means,sems = test_rate(method,rates=(5,10,20,40),data_type='timestamp',n_trials=1000,
                           do_tests=True,do_plots=False,plot_dir=None,seed=1, **kwargs)

    ARGS
    method      String. Name of rate estimation function to test: 'bin' | 'density'

    rates       (n_rates,) array-like. List of expected spike rates to test
                Default: (5,10,20,40)

    data_type   String. Type of spiking data to input into rate functions:
                'timestamp' [default] | 'bool' (0/1 binary spike train)

    n_trials    Int. Number of trials to include in simulated data. Default: 1000

    do_tests    Bool. Set=True to evaluate test results against expected values and
                raise an error if they fail. Default: True

    do_plots    Bool. Set=True to plot test results. Default: False

    plot_dir    String. Full-path directory to save plots to. Set=None [default] to not save plots.

    seed        Int. Random generator seed for repeatable results.
                Set=None for fully random numbers. Default: 1 (reproducible random numbers)

    **kwargs All other keyword args passed to rate estimation function

    RETURNS
    means       (n_rates,) ndarray. Estimated mean rate for each expected rate

    sems        (n_rates,) ndarray. SEM of mean rate for each expected rate

    passed      Bool. True if estimated results pass all tests; otherwise False.

    ACTION
    If do_tests is True, raises an error if any estimated stat is too far from expected value
    If do_plots is True, also generates a plot summarizing expected vs estimated rates
    """
    assert data_type in ['timestamp','bool'], \
        ValueError("Unsupported value '%s' given for data_type. Should be 'timestamp' | 'bool"
                   % data_type)

    if method == 'bin':
        n_timepts = 20
        tbool     = np.ones((n_timepts,),dtype=bool)

    elif method == 'density':
        n_timepts = 1001
        # HACK For spike density method, remove edges, which are influenced by boundary artifacts
        timepts   = np.arange(0,1.001,0.001)
        tbool     = (timepts > 0.1) & (timepts < 0.9)

    else:
        raise ValueError("Unsupported option '%s' given for <method>. \
                         Should be 'bin_rate'|'density'" % method)

    rates = np.asarray(rates)

    means = np.empty((len(rates),))
    sems = np.empty((len(rates),))
    if do_plots: time_series = np.empty((n_timepts,len(rates)))

    for i,rate in enumerate(rates):
        # Generate simulated spike train data
        trains,_ = simulate_spike_trains(gain=0.0,offset=float(rate),data_type='timestamp',
                                         n_conds=1,n_trials=n_trials,seed=seed)

        # Convert spike timestamps -> binary 0/1 spike trains (if requested)
        if data_type == 'bool':
            trains,timepts = times_to_bool(trains,lims=[0,1])
            kwargs.update(timepts=timepts)      # Need <timepts> input for bool data

        # Compute spike rate from simulated spike trains -> (n_trials,n_timepts)
        spike_rates,timepts = rate(trains, method=method, lims=[0,1], **kwargs)
        if method == 'bin': timepts = timepts.mean(axis=1)  # bins -> centers

        if do_plots: time_series[:,i] = spike_rates.mean(axis=0)
        # Take average across timepoints -> (n_trials,)
        spike_rates = spike_rates[:,tbool].mean(axis=1)

        # Compute mean and SEM across trials
        means[i] = spike_rates.mean(axis=0)
        sems[i]  = spike_rates.std(axis=0,ddof=0) / sqrt(n_trials)

    # Optionally plot summary of test results
    if do_plots:
        plt.figure()
        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

        # Plot time course of estimated rates
        ax = plt.subplot(1,2,1)
        ylim = (0,1.05*time_series.max())
        for i,rate in enumerate(rates):
            plt.plot(timepts, time_series[:,i], '-', color=colors[i], linewidth=1.5)
            plt.text(0.99, (0.95-0.05*i)*ylim[1], np.round(rate,decimals=2),
                     color=colors[i], fontweight='bold', horizontalalignment='right')
        plt.grid(axis='both',color=[0.75,0.75,0.75],linestyle=':')
        plt.ylim(ylim)
        plt.xlabel('Time')
        plt.ylabel('Estimated rate')

        # Plot across-time mean rates
        ax = plt.subplot(1,2,2)
        ax.set_aspect('equal', 'box')
        plt.grid(axis='both',color=[0.75,0.75,0.75],linestyle=':')
        plt.plot([0,1.1*rates[-1]], [0,1.1*rates[-1]], '-', color='k', linewidth=1)
        plt.errorbar(rates, means, 3*sems, marker='o')
        plt.xlabel('Simulated rate (spk/s)')
        plt.ylabel('Estimated rate')
        if plot_dir is not None:
            plt.savefig(os.path.join(plot_dir,'rate-%s-%s.png' % (method,data_type)))

    # Determine if any estimated rates are outside acceptable range (expected mean +/- 3*SEM)
    errors = np.abs(means - rates) / sems

    # Find estimates that are clearly wrong
    passed = True
    bad_estimates = (errors > 3.3)
    if bad_estimates.any():
        passed = False
        if do_plots: plt.plot(rates[bad_estimates], means[bad_estimates]+0.1, '*', color='k')
        if do_tests:    raise AssertionError("%d tested rates failed" % bad_estimates.sum())
        else:           warn("%d tested rates failed" % bad_estimates.sum())

    return means, sems, passed


# =============================================================================
# Tests for rate stats functions
# =============================================================================
def test_rate_stats(stat, test='mean', test_values=None, distribution='poisson', n_trials=1000,
                    n_reps=100, do_tests=True, do_plots=False, plot_dir=None, seed=1, **kwargs):
    """
    Basic testing for functions estimating spike rate statistics

    Generates synthetic spike rate data with given parameters,
    estimates stats using given function, and compares estimated to expected.

    means,sds,passed = test_rate_stats(stat,test='mean',test_values=None,distribution='poisson',
                                       n_trials=1000,n_reps=100,do_tests=True,do_plots=False,
                                       plot_dir=None, seed=1, **kwargs)

    ARGS
    stat        String. Name of rate stat to test: 'Fano' | 'CV'

    test        String. Type of test to run. Default: 'rate'. Options: 'rate' | 'spread'

    test_values (n_values,) array-like. List of values to test.
                Interpretation and defaults are test-specific:
                'mean'      Mean spike rate. Default: [1,2,5,10,20]
                'spread'    Gaussian SDs for generating rates. Default: [1,2,5,10,20]
                'n'         Trial numbers. Default: [25,50,100,200,400,800]

    distribution String. Name of distribution to simulate data from.
                Options: 'normal' | 'poisson' [default]

    n_trials    Int. Number of trials to simulate data for. Default: 1000

    do_tests    Bool. Set=True to evaluate test results against expected values and
                raise an error if they fail. Default: True

    do_plots    Bool. Set=True to plot test results. Default: False

    plot_dir    String. Full-path directory to save plots to. Set=None [default] to not save plots.

    seed        Int. Random generator seed for repeatable results.
                Set=None for fully random numbers. Default: 1 (reproducible random numbers)

    RETURNS
    means       (n_test_values,) ndarray. Mean of estimated stat values across reps.

    sems        (n_test_values,) ndarray. Std dev of estimated stat values across reps.

    passed      Bool. True if estimated results pass all tests; otherwise False.

    ACTION
    If do_tests is True, raises an error if any estimated stat is too far from expected value
    If do_plots is True, also generates a plot summarizing results
    """
    # Note: Set random seed once here, not for every random data generation loop below
    if seed is not None: np.random.seed(seed)

    stat = stat.lower()
    test = test.lower()
    distribution = distribution.lower()
    if test in ['spread','spreads','sd']:
        assert distribution != 'poisson', \
            "Can't run 'spread' test with Poisson data (variance is fixed ~ mean rate)"

    # Set defaults for tested values and set up data generator function depending on <test>
    # Note: Only set random seed once above, don't reset in data generator function calls
    # todo Should we move some/all of these into function arguments, instead of hard-coding?
    sim_args = dict(gain=5.0, offset=0.0, spreads=5.0, n_conds=1, n=n_trials,
                    distribution=distribution, seed=None)

    if test in ['mean','rate','gain']:
        test_values = [1,2,5,10,20] if test_values is None else test_values
        del sim_args['gain']                    # Delete preset arg so uses arg to lambda below
        gen_data = lambda mean: simulate_dataset(**sim_args,gain=mean)

    elif test in ['spread','spreads','sd']:
        test_values = [1,2,5,10,20] if test_values is None else test_values
        del sim_args['spreads']                 # Delete preset arg so uses arg to lambda below
        gen_data = lambda spread: simulate_dataset(**sim_args,spreads=spread)

    elif test in ['n','n_trials']:
        test_values = [25,50,100,200,400,800] if test_values is None else test_values
        del sim_args['n']                       # Delete preset arg so uses arg to lambda below
        gen_data = lambda n_trials: simulate_dataset(**sim_args,n=n_trials)

    else:
        raise ValueError("Unsupported value '%s' set for <test>" % test)

    stat_values = np.empty((len(test_values),n_reps))
    for i_value,test_value in enumerate(test_values):
        for i_rep in range(n_reps):
            # Generate simulated data with current test value
            data,_ = gen_data(test_value)

            stat_values[i_value,i_rep] = rate_stats(data, stat=stat, axis=0)

    # Compute mean and std dev across different reps of simulation
    stat_sds    = stat_values.std(axis=1,ddof=0)
    stat_means  = stat_values.mean(axis=1)

    if do_plots:
        plt.figure()
        plt.grid(axis='both',color=[0.75,0.75,0.75],linestyle=':')
        plt.errorbar(test_values, stat_means, stat_sds, marker='o')
        xlabel = 'n' if test == 'bias' else test
        plt.xlabel(xlabel)
        plt.ylabel("%s(rate)" % stat)
        if plot_dir is not None:
            plt.savefig(os.path.join(plot_dir,'stat-summary-%s-%s-%s' % (stat,test,distribution)))

    # Determine if test actually produced the expected values
    # 'mean' : Test if stat decreases monotonically with mean rate for normal data,
    #           remains ~ same for Poisson
    if test == 'mean':
        if distribution == 'normal':
            evals = [((np.diff(stat_means) <= 0).all(),
                      "%s does not deccrease monotonically with increase in mean" % stat)]
        elif distribution == 'poisson':
            evals = [(stat_means.ptp() < stat_sds.max(),
                      "%s has larger than expected range for increase in mean of Poisson data"
                      % stat)]

    # 'spread' : Test if stat increases monotonically with increasing distribution spread (rate SD)
    elif test in ['spread','spreads','sd']:
        evals = [((np.diff(stat_means) >= 0).all(),
                  "%s does not increase monotonically with spread increase" % stat)]

    # 'n' : Test if stat is ~ same for all values of n (unbiased by n)
    elif test in ['n','n_trials']:
        evals = [(stat_means.ptp() < stat_sds.max(),
                  "%s has larger than expected range across n's (likely biased by n)" % stat)]

    passed = True
    for cond,message in evals:
        if not cond:    passed = False

        # Raise an error for test fails if do_tests is True
        if do_tests:    assert cond, AssertionError(message)
        # Just issue a warning for test fails if do_tests is False
        elif not cond:  warn(message)

    return stat_means, stat_sds, passed


def rate_stat_test_battery(stats=('fano','cv'), tests=('mean','spread','n'),
                           distributions=('normal','poisson'), do_tests=True, **kwargs):
    """
    Runs a battery of given tests on given spike rate statistic computation methods

    rate_stat_test_battery(stats=('fano','cv'), tests=('mean','spread','n'),
                           distributions=('normal','poisson'), do_tests=True,**kwargs)

    ARGS
    stats       Array-like. List of spike rate stats to evaluate.
                Default: ('fano','cv') (all supported methods)

    tests       Array-like. List of tests to run.
                Default: ('mean','spread','n') (all supported tests)

    distributions Array-like. List of data distributions to test.
                Default: ('normal','poisson') (all supported tests)

    do_tests    Bool. Set=True to evaluate test results against expected values and
                raise an error if they fail. Default: True

    kwargs      Any other kwargs passed directly to test_randstats()

    ACTION
    If do_tests is True, raises an error if any estimated value for any (stat,test)
    is too far from expected value
    """
    if isinstance(stats,str): stats = [stats]
    if isinstance(tests,str): tests = [tests]

    for stat in stats:
        for test in tests:
            for distribution in distributions:
                print("Running %s test on %s %s" % (test,stat,distribution))

                # Skip test of distribution spread (SD) for Poisson, bc SD is defined by mean
                if (test.lower() == 'spread') and (distribution.lower() == 'poisson'): continue

                t1 = time.time()

                _,_,passed = test_rate_stats(stat, test=test, distribution=distribution,
                                             do_tests=do_tests, **kwargs)

                print('%s (test ran in %.1f s)' %
                      ('PASSED' if passed else 'FAILED', time.time()-t1))
                if 'plot_dir' in kwargs: plt.close('all')


# =============================================================================
# Tests for ISI stats functions
# =============================================================================
def test_isi_stats(stat, test='mean', test_values=None, n_reps=100,
                   do_tests=True, do_plots=False, plot_dir=None, seed=1, **kwargs):
    """
    Basic testing for functions estimating inter-spike interval statistics

    Generates synthetic spike train data with given parameters,
    estimates ISI stats using given function, and compares estimated to expected.

    means,sds,passed = test_isi_stats(stat,test='mean',test_values=None,n_reps=100,
                                      do_tests=True,do_plots=False, plot_dir=None, seed=1, **kwargs)

    ARGS
    stat        String. Name of ISI stat to test: 'Fano' | 'CV' | 'CV2 | 'LV' | 'burst_fract'

    test        String. Type of test to run. Default: 'mean'

    test_values (n_values,) array-like. List of values to test.
                Interpretation and defaults are test-specific:
                'mean'      Mean spike rate. Default: [1,2,5,10,20]

    n_reps      Int. Number of indpendent repetitions of test to run. Default: 100

    do_tests    Bool. Set=True to evaluate test results against expected values and
                raise an error if they fail. Default: True

    do_plots    Bool. Set=True to plot test results. Default: False

    plot_dir    String. Full-path directory to save plots to. Set=None [default] to not save plots.

    seed        Int. Random generator seed for repeatable results.
                Set=None for fully random numbers. Default: 1 (reproducible random numbers)

    RETURNS
    means       (n_test_values,) ndarray. Mean of estimated stat values across reps.

    sems        (n_test_values,) ndarray. Std dev of estimated stat values across reps.

    passed      Bool. True if estimated results pass all tests; otherwise False.

    ACTION
    If do_tests is True, raises an error if any estimated stat is too far from expected value
    If do_plots is True, also generates a plot summarizing results
    """
    # Note: Set random seed once here, not for every random data generation loop below
    if seed is not None: np.random.seed(seed)

    stat = stat.lower()
    test = test.lower()

    # Set defaults for tested values and set up data generator function depending on <test>
    # Set up to run simulation for 10 s to get good estimates, and for n_reps separate trials
    # Note: Only set random seed once above, don't reset in data generator function calls
    # todo Should we move some/all of these into function arguments, instead of hard-coding?
    sim_args = dict(gain=0.0, offset=5.0, n_conds=1, n_trials=n_reps, time_range=10.0, seed=None)

    if test in ['mean','rate','gain']:
        test_values = [1,2,5,10,20] if test_values is None else test_values
        del sim_args['offset']              # Delete preset arg so it uses argument to lambda below
        gen_data = lambda mean: simulate_spike_trains(**sim_args,offset=float(mean))

    else:
        raise ValueError("Unsupported value '%s' set for <test>" % test)

    stat_values = np.empty((len(test_values),n_reps))
    for i_value,test_value in enumerate(test_values):
        # Generate simulated spike timestamp data with current test value
        data,_  = gen_data(test_value)
        ISIs    = isi(data)

        stat_values[i_value,:] = isi_stats(ISIs, stat=stat, axis='each')

    # Compute mean and std dev across different reps of simulation
    stat_sds    = stat_values.std(axis=1,ddof=0)
    stat_means  = stat_values.mean(axis=1)

    if do_plots:
        plt.figure()
        plt.grid(axis='both',color=[0.75,0.75,0.75],linestyle=':')
        plt.errorbar(test_values, stat_means, stat_sds, marker='o')
        xlabel = 'n' if test == 'bias' else test
        plt.xlabel(xlabel)
        plt.ylabel("%s(ISI)" % stat)
        if plot_dir is not None:
            plt.savefig(os.path.join(plot_dir,'stat-summary-%s-%s' % (stat,test)))

    # Determine if test actually produced the expected values
    # 'mean' : Test if stat remains ~ same for Poisson
    if test == 'mean':
        evals = [(stat_means.ptp() < stat_sds.max(),
                 "%s has larger than expected range for increase in mean of Poisson data" % stat)]

    passed = True
    for cond,message in evals:
        if not cond:    passed = False

        # Raise an error for test fails if do_tests is True
        if do_tests:    assert cond, AssertionError(message)
        # Just issue a warning for test fails if do_tests is False
        elif not cond:  warn(message)

    return stat_means, stat_sds, passed


def isi_stat_test_battery(stats=('Fano','CV','CV2','LV','burst_fract'), tests=('mean'),
                          do_tests=True, **kwargs):
    """
    Runs a battery of given tests on given inter-spike interval statistic computation methods

    isi_stat_test_battery(stats=('Fano','CV','CV2','LV','burst_fract'),tests=('mean'),
                          do_tests=True,**kwargs)

    ARGS
    stats       Array-like. List of ISI stats to evaluate.
                Default: ('Fano','CV','CV2','LV','burst_fract') (all supported methods)

    tests       Array-like. List of tests to run.
                Default: ('mean') (all supported tests)

    do_tests    Bool. Set=True to evaluate test results against expected values and
                raise an error if they fail. Default: True

    kwargs      Any other kwargs passed directly to test_randstats()

    ACTION
    If do_tests is True, raises an error if any estimated value for any (stat,test)
    is too far from expected value
    """
    if isinstance(stats,str): stats = [stats]
    if isinstance(tests,str): tests = [tests]

    for stat in stats:
        for test in tests:
            print("Running %s test on %s" % (test,stat))
            do_tests_ = False if (stat == 'burst_fract') and (test == 'mean') else do_tests

            t1 = time.time()

            _,_,passed = test_isi_stats(stat, test=test, do_tests=do_tests_, **kwargs)

            print('%s (test ran in %.1f s)' % ('PASSED' if passed else 'FAILED', time.time()-t1))
            if 'plot_dir' in kwargs: plt.close('all')


# =============================================================================
# Tests for plotts functions
# =============================================================================
def test_plot_mean_waveforms(plot_dir=None):
    """
    Basic testing for plotting function plot_mean_waveforms()

    ARGS
    plot_dir String. Full-path directory to save plots to. Set=None [default] to not save plots.

    ACTIONS Creates a plot and optionally saves it to PNG file
    """
    n_units = 3
    n_spikes = 100
    n_timepts = 1000

    # Use dpss tapers as data to plot, since they are all very distinct looking
    means = compute_tapers(n_timepts, time_width=1.0, freq_width=4, n_tapers=n_units)
    waveforms = np.empty((n_units,), dtype=object)
    for unit in range(n_units):
        waveforms[unit] = means[:,[unit]] + np.random.standard_normal((n_timepts,n_spikes))
        
    # Basic test plot
    plt.figure()
    plot_mean_waveforms(waveforms, plot_sd=True)
    plt.title('Basic test plot')
    plt.show()
    if plot_dir is not None: plt.savefig(os.path.join(plot_dir,'plot_mean_waveforms.png'))
            
    # Plot w/o SDs (means only)
    plt.figure()
    plot_mean_waveforms(waveforms, plot_sd=False)
    plt.title('Means-only plot')
    plt.show()
    if plot_dir is not None: plt.savefig(os.path.join(plot_dir,'plot_mean_waveforms-noSD.png'))
            
            
def test_plot_waveform_heatmap(plot_dir=None):
    """
    Basic testing for plotting function plot_waveform_heatmap()

    ARGS
    plot_dir String. Full-path directory to save plots to. Set=None [default] to not save plots.

    ACTIONS Creates a plot and optionally saves it to PNG file
    """
    n_units = 1
    n_spikes = 100
    n_timepts = 1000

    # Use dpss tapers as data to plot, since they are all very distinct looking
    means = compute_tapers(n_timepts, time_width=1.0, freq_width=4, n_tapers=n_units)
    waveforms = np.empty((n_units,), dtype=object)
    for unit in range(n_units):
        waveforms[unit] = means[:,[unit]] + np.random.standard_normal((n_timepts,n_spikes))
        
    # Basic test plot
    plt.figure()
    plot_waveform_heatmap(waveforms)
    plt.title('Basic test plot')
    if plot_dir is not None: plt.savefig(os.path.join(plot_dir,'plot_waveform_heatmap.png'))
            
    # Basic test plot
    plt.figure()
    plot_waveform_heatmap(waveforms, n_ybins=50)
    plt.title('Fine-grained bins')
    if plot_dir is not None: plt.savefig(os.path.join(plot_dir,'plot_waveform_heatmap-50bins.png'))
                        