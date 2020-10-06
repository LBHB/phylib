# -*- coding: utf-8 -*-

"""Test template loading functions."""


#------------------------------------------------------------------------------
# Imports
#------------------------------------------------------------------------------

import logging
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np
import numpy.random as npr
from numpy.testing import assert_allclose as ac
from pytest import raises

from .conftest import Dataset
from phylib.utils import Bunch
from .. import loader as l

logger = logging.getLogger(__name__)


#------------------------------------------------------------------------------
# Test format utils
#------------------------------------------------------------------------------

def test_are_templates_dense(dset):
    if dset.param == 'ks2':
        assert l._are_templates_dense(dset.tempdir)


def test_are_features_dense(dset):
    if dset.param == 'ks2':
        assert not l._are_features_dense(dset.tempdir)


def test_are_template_features_dense(dset):
    if dset.param == 'ks2':
        assert not l._are_template_features_dense(dset.tempdir)


#------------------------------------------------------------------------------
# Test computations
#------------------------------------------------------------------------------

def test_compute_spike_depths_from_features():
    ns, nf, nc = 4, 2, 3

    fet = 5 + npr.randn(ns, nf, nc)
    ch = np.tile(np.arange(nc), (ns, 1))
    features = Bunch(data=fet, cols=ch)

    st = [0, 0, 1, 1]
    channel_pos = np.array([[0, 100], [0, 200], [0, 300]])

    features_dense = Bunch(data=fet)
    for batch in (50_000, 2):
        for F in (features, features_dense):
            sd = l._compute_spike_depths_from_features(F, st, channel_pos, batch=batch)
            assert sd.dtype == np.float64
            assert sd.ndim == 1
            assert sd.shape == (ns,)
            assert np.all((10 <= sd) & (sd <= 1000))


def test_normalize_templates_waveforms():
    nt, nw, nc = 3, 4, 2
    w = npr.randn(nt, nw, nc)
    ch = npr.permutation(nt * nc).reshape((nt, nc))
    ns = 6
    amp = [1, 1, 2, 2, 3, 5]
    st = [0, 0, 1, 1, 2, 2]
    tw = l._normalize_templates_waveforms(
        w, ch, amplitudes=amp, n_channels=nc, spike_templates=st, amplitude_threshold=0)

    assert tw.data.shape == (nt, nw, nc)
    assert tw.cols.shape == (nt, nc)
    assert tw.spike_amps.shape == (ns,)
    assert tw.template_amps.shape == (nt,)

    assert np.all(tw.spike_amps > 0)
    assert np.all(tw.template_amps > 0)


def test_normalize_templates_waveforms_ks2(dset):
    if dset.param != 'ks2':
        return
    params = l.read_params(dset.params_path)
    w = dset.load('templates.npy')
    nt, nsmp = w.shape[:2]
    ch = dset.load('templates_ind.npy')
    amp = dset.load('amplitudes.npy')
    st = dset.load('spike_templates.npy')
    nspk = st.shape[0]
    unw_mat = dset.load('whitening_mat_inv.npy')
    ampfactor = params['ampfactor']

    nc = 16
    at = .25

    tw = l._normalize_templates_waveforms(
        w, ch, amplitudes=amp, n_channels=nc, spike_templates=st,
        unw_mat=unw_mat, ampfactor=ampfactor,
        amplitude_threshold=at)
    templates = tw.data
    channels = tw.cols
    spike_amps = tw.spike_amps
    template_amps = tw.template_amps

    assert templates.shape == (nt, nsmp, nc)
    assert channels.shape == (nt, nc)
    assert spike_amps.shape == (nspk,)
    assert template_amps.shape == (nt,)

    assert np.all(-6e-4 <= templates)
    assert np.all(templates <= 6e-4)

    assert np.all(channels >= -1)
    assert np.all(channels <= params['n_channels_dat'])

    assert np.all(1e-6 <= spike_amps)
    assert np.all(spike_amps <= 1e-3)

    assert np.all(template_amps <= 1e-3)


#------------------------------------------------------------------------------
# Test loading helpers
#------------------------------------------------------------------------------

# Spike times
#------------

def test_load_spike_times_ks2():
    ac(l._load_spike_times_ks2([0, 10, 100], 10.), [0, 1, 10])
    ac(l._load_spike_reorder_ks2([0, 10, 100], 10.), [0, 1, 10])


def test_load_spike_times_alf():
    ac(l._load_spike_times_alf([0., 1., 10.]), [0, 1, 10])


def test_validate_spike_times():
    wrong = [[-1, 1], [2, 3, 7, 5]]
    sr = 10
    for st in wrong:
        with raises(ValueError):
            l._load_spike_times_ks2(st, sr)
        with raises(ValueError):
            l._load_spike_times_alf(st)


# Spike templates
#----------------

def test_load_spike_templates():
    ac(l._load_spike_templates([0, 0, 5, -1]), [0, 0, 5, -1])


# Channels
#---------

def test_load_channel_map():
    ac(l._load_channel_map([0, 1, 3, 2]), [0, 1, 3, 2])
    with raises(ValueError):
        l._load_channel_map([0, 1, 2, 2])


def test_load_channel_positions():
    ac(l._load_channel_positions([[0, 0], [1, 0]]), [[0, 0], [1, 0]])
    with raises(ValueError):
        l._load_channel_positions([0, 0, 1, 2])
    with raises(ValueError):
        l._load_channel_positions([[0, 0, 1, 2]])
    # Duplicate channels should not raise an error, but default to a linear probe with
    # an error message.
    ac(l._load_channel_positions([[0, 0], [0, 0]]), [[0, 0], [0, 1]])


def test_load_channel_shanks():
    ac(l._load_channel_shanks([0, 0, 1, 2]), [0, 0, 1, 2])


def test_load_channel_probes():
    ac(l._load_channel_probes([0, 0, 1, 2]), [0, 0, 1, 2])


# Waveforms
# ---------

def test_load_template_waveforms():
    ns, nw, nc = 3, 4, 2
    w = npr.randn(ns, nw, nc)
    ch = npr.permutation(ns * nc).reshape((ns, nc))
    tw = l._load_template_waveforms(w, ch)
    assert tw.data.shape == (ns, nw, nc)
    assert tw.cols.shape == (ns, nc)


def test_load_spike_waveforms():
    ns, nw, nc = 3, 4, 2
    w = npr.randn(ns, nw, nc)
    ch = npr.permutation(ns * nc).reshape((ns, nc))
    tw = l._load_spike_waveforms(w, ch, [2, 3, 5])
    assert tw.data.shape == (ns, nw, nc)
    assert tw.cols.shape == (ns, nc)
    assert tw.rows.shape == (ns,)


# Features
# ---------

def test_load_features():
    ns, nc, nf = 3, 4, 2
    w = npr.randn(ns, nc, nf)
    ch = npr.permutation(ns * nc).reshape((ns, nc))
    fet = l._load_features(w, ch, [2, 3, 5])
    assert fet.data.shape == (ns, nc, nf)
    assert fet.cols.shape == (ns, nc)
    assert fet.rows.shape == (ns,)


def test_load_template_features():
    ns, nc = 3, 4
    w = npr.randn(ns, nc)
    ch = npr.permutation(2 * nc).reshape((2, nc))
    fet = l._load_template_features(w, ch, [2, 3, 5])
    assert fet.data.shape == (ns, nc)
    assert fet.cols.shape == (2, nc)
    assert fet.rows.shape == (ns,)


# Amplitudes
# ----------

def test_load_amplitudes_alf():
    amp = npr.uniform(low=1e-4, high=1e-2, size=10)
    ac(l._load_amplitudes_alf(amp), amp)
    with raises(Exception):
        l._load_amplitudes_alf([-1])


# Depths
# ------

def test_load_depths_alf():
    depths = npr.uniform(low=0, high=1e3, size=10)
    ac(l._load_depths_alf(depths), depths)
    with raises(Exception):
        l._load_depths_alf([-1])


# Whitening matrix
# ----------------

def test_load_whitening_matrix():
    wm0 = npr.randn(5, 5)

    wm, wmi = l._load_whitening_matrix(wm0, inverse=False)
    ac(wm, wm0)
    ac(wm @ wmi, np.eye(5), atol=1e-10)

    wm, wmi = l._load_whitening_matrix(wm0, inverse=True)
    ac(wmi, wm0)
    ac(wm @ wmi, np.eye(5), atol=1e-10)


# Template similarity matrix
# --------------------------

def test_load_similarity_matrix():
    mat0 = npr.randn(5, 5)
    mat = l._load_similarity_matrix(mat0)
    ac(mat, mat0)


#------------------------------------------------------------------------------
# Test loading functions
#------------------------------------------------------------------------------

class TemplateLoaderDenseTests(unittest.TestCase):
    param = 'dense'

    @ classmethod
    def setUpClass(cls):
        cls.ibl = cls.param in ('ks2', 'alf')
        cls.tempdir = Path(tempfile.mkdtemp())
        cls.dset = Dataset(cls.tempdir, cls.param)

    @ classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tempdir)

    def test_spike_times(self):
        pass


#------------------------------------------------------------------------------
# Other datasets
#------------------------------------------------------------------------------

class TemplateLoaderSparseTests(TemplateLoaderDenseTests):
    param = 'sparse'


class TemplateLoaderMiscTests(TemplateLoaderDenseTests):
    param = 'misc'


#------------------------------------------------------------------------------
# IBL datasets
#------------------------------------------------------------------------------

class TemplateLoaderKS2Tests(TemplateLoaderDenseTests):
    param = 'ks2'
    _loader_cls = l.TemplateLoaderKS2

    @ classmethod
    def setUpClass(cls):
        cls.ibl = True
        cls.tempdir = Path(tempfile.mkdtemp())
        cls.dset = Dataset(cls.tempdir, cls.param)

        ld = cls.loader = cls._loader_cls()
        ld.open(cls.tempdir)


class TemplateLoaderALFTests(TemplateLoaderKS2Tests):
    param = 'alf'
    _loader_cls = l.TemplateLoaderAlf

    def test_spike_waveforms(self):
        nspk, nsmp, nch = self.loader.spike_waveforms.data.shape
        assert self.loader.spike_waveforms.cols.shape == (nspk, nch)
        assert self.loader.spike_waveforms.rows.shape == (nspk,)


class TemplateLoaderIBLTests(unittest.TestCase):
    @ classmethod
    def setUpClass(cls):
        cls.tempdir = Path(tempfile.mkdtemp())

        cls.dset_ks2 = Dataset(cls.tempdir / 'ks2', 'ks2')
        cls.loader_ks2 = l.TemplateLoaderKS2()
        cls.loader_ks2.open(cls.tempdir / 'ks2')

        cls.dset_alf = Dataset(cls.tempdir / 'alf', 'alf')
        cls.loader_alf = l.TemplateLoaderAlf()
        cls.loader_alf.open(cls.tempdir / 'alf')

    def test_ibl_1(self):
        la = self.loader_alf
        lk = self.loader_ks2

        dt = np.abs(la.spike_times - lk.spike_times)
        self.assertLessEqual(dt.max(), 1e-3)

        xs = (
            'spike_templates',
            'spike_clusters',
            'channel_map',
            'channel_positions',
            'channel_shanks',
            'channel_probes',
            'spike_depths',
            'spike_amps',
            'wm',
            'wmi',
        )
        for x in xs:
            self.assertTrue(np.all(getattr(la, x) == getattr(lk, x)))

        assert .5 <= la.template_amps.mean() / lk.template_amps.mean() <= 1.5
        assert .5 <= la.template_amps.std() / lk.template_amps.std() <= 1.5

        ta = l.from_sparse(np.transpose(
            la.templates.data[:1, ...], (0, 2, 1)),
            la.templates.cols[:1, ...], np.arange(la.n_channels))
        tk = l.from_sparse(np.transpose(
            lk.templates.data[:1, ...], (0, 2, 1)),
            lk.templates.cols[:1, ...], np.arange(lk.n_channels))

        assert .5 <= ta.mean() / tk.mean() <= 1.5
        assert .5 <= ta.std() / tk.std() <= 1.5

        # import matplotlib.pyplot as plt
        # plt.subplot(121)
        # plt.plot(ta[0].T)
        # plt.subplot(122)
        # plt.plot(tk[0].T)
        # plt.show()
