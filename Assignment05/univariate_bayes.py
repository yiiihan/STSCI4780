"""
Module defining a base class implementing simple Bayesian inference for a
univariate model, using quadrature for integration.

Created Feb 27, 2015 by Tom Loredo
2020-03-05:  Revised for BDA20
2022-03-25:  Revised by Yi Han for BDA22 HW5
"""

import numpy as np
from numpy import *
from numpy.random import rand
from scipy.optimize import minimize_scalar
from matplotlib.pyplot import plot
import scipy
from scipy.stats import norm
import random


# Note:  The "object" base class provides some extra inheritance capability;
# it's the default in Python 3.


rt2pi = sqrt(2*pi)


class UnivariateBayesianInference(object):
    """
    Implement Bayesian inference for a univariate model, using quadrature for
    integrals.
    """

    def __init__(self, param_grid, prior, lfunc=None, llfunc=None):
        """
        Calculate the posterior distribution over a grid in parameter space.

        Either the likelihood or the log-likelihood may be specified.

        Parameters
        ----------
        param_grid : float array
            Array of parameter values; assumed equally spaced

        prior : float or function
            Prior PDF for the param, as a constant for flat prior, or
            a function that can evaluate the PDF on an array

        lfunc : function
            Function that can evaluate the likelihood on an array

        llfunc : function
            Function that can evaluate the log-likelihood on an array
        """
        self.param_grid = param_grid
        self.delta = param_grid[1] - param_grid[0]
        self.prior = prior
        self.lfunc = lfunc
        self.llfunc = llfunc

        # Evaluate prior and likelihood over the grid.
        self.qvals = self.quasi(param_grid)

        # Bayes's theorem, using the trapezoid rule for the marginal likeilhood:
        self.mlike = np.trapz(self.qvals, dx=self.delta)
        self.post_pdf = self.qvals/self.mlike

        # Info for accept/reject method:
        self.span = param_grid[-1] - param_grid[0]
        self.max_pdf = self.post_pdf.max()
        self.n_ar = 0  # count iterations for efficiency estimates

        # Calculate posterior mean and std devn.
        self.post_mean = np.trapz(self.param_grid*self.post_pdf, dx=self.delta)
        m2 = np.trapz(self.param_grid**2 * self.post_pdf, dx=self.delta)
        self.post_std = sqrt(m2 - self.post_mean**2)

        # Calculate the posterior CDF on the grid.
        self.post_cdf = zeros_like(self.post_pdf)
        for i in range(1, len(param_grid)):
            dp = 0.5*self.delta*(self.post_pdf[i-1] + self.post_pdf[i])
            self.post_cdf[i] = self.post_cdf[i-1] + dp

        # Find the location and q() value for the posterior mode; this is
        # used for Laplace approximations and for accept/reject sampling.
        # First just locate the max on the grid.
        i_max = self.post_pdf.argmax()
        # If the mode is on a boundary, then no refinement is necessary;
        # otherwise, optimize to refine the mode.
        if i_max == 0 or i_max == len(param_grid):  # mode on a boundary
            self.mode = param_grid[i_max]
            self.mode_q = self.qvals[i_max]
        else:  # optimize to find the mode
            # Starting values for bracketing mode.
            a, c = self.param_grid[i_max-1], self.param_grid[i_max+1]
            bounds = self.param_grid[0], self.param_grid[-1]
            results = minimize_scalar(self._neg_log_q, (a, c), bounds)
            self.mode = results.x
            self.mode_q = exp(-results.fun)
        self.mode_pdf = self.mode_q/self.mlike

    def quasi(self, param_vals):
        """
        Return the product of the prior pdf and the likelihood function---the
        quasiposterior---for the provided param values (scalar or vector).
        """
        param_vals = asarray(param_vals)  # to handle sequence & scalar inputs
        if callable(self.prior):
            prior_vals = self.prior(param_vals)
        else:
            prior_vals = self.prior*ones_like(param_vals)
        if self.lfunc:
            if self.llfunc:
                raise ValueError('Cannot specify both lfunc & llfunc!')
            like_vals = self.lfunc(param_vals)
        else:  # *** This option is so far untested!
            if self.llfunc is None:
                raise ValueError('Must specify either lfunc or llfunc!')
            like_vals = self.llfunc(param_vals)
            # Subtract off the max to avoid possible underflow everywhere;
            # note this affects the marginal likelihood so it needs to be
            # taken into account if the marginal likelihood is used directly,
            # e.g., to compute a Bayes factor.
            like_vals = exp(like_vals - like_vals.max())
        return prior_vals*like_vals
    

    def _neg_log_q(self, param):
        """
        Return the negative log prior*likelihood, for optimization; `param`
        should be a single (scalar) parameter value.
        """
        return -log(self.quasi(param))

    def pdf(self, param_vals):
        """
        Return the posterior density for the provided param values
        (scalar or vector).
        """
        return self.quasi(param_vals)/self.mlike

    def laplace(self, g=None):
        """
        Calculate the Laplace approximation for the integral of a function
        g() times the (unnormalize) posterior PDF.  If g=None, a constant
        function, g=1, is used, and the estimated marginal likelihood is
        returned.

        Parameters
        ----------
        g : float function
            Function whose (unnormalized) expectation will be approximated;
            should accept scalar or vector inputs

        Returns
        -------
        ampl, locn, sig, est : floats
            The amplitude, location, and std devn of a Gaussian approx'n to
            the integrand, and the Laplace approx'n for the integral
        """
        # Gather the g() values on param_grid.
        if g is None:
            def g(param_vals):
                param_vals = asarray(param_vals)
                return ones_like(param_vals)
        gvals = g(self.param_grid)
        # Find the peak of g*q on the grid.
        gqvals = gvals * self.qvals
        i_max = gqvals.argmax()
        if i_max == 0 or i_max == len(self.param_grid):
            raise ValueError('Laplace not possible; peak is on a boundary!')

        # Refine the peak via optimization of -log(g*q).

        # Define a target function for SciPy's optimizer, which minimizes
        # a function of a scalar argument.
        def f_opt(param):
            return -log(g(param)) + self._neg_log_q(param)
            #return -log(g(param))-log(self.quasi(param))

        # Starting values for bracketing mode.
        a, c = self.param_grid[i_max-1], self.param_grid[i_max+1]
        bounds = self.param_grid[0], self.param_grid[-1]
        results = minimize_scalar(f_opt, (a, c), bounds)
        locn = results.x
        ampl = exp(-results.fun)
        

        # Find the curvature via 2nd differencing.
        # YOUR CODE HERE:  CALCULATE & RETURN ampl, locn, sig, est
        diff=(f_opt(a)+f_opt(c)-2*f_opt(locn))/((locn-a)*(c-locn)) #calculate the 2nd differencing at mode by finite differencing
        var=1/diff
        sig=sqrt(var)
        
        #matching peak
        norm_peak=norm.pdf(locn,loc=locn,scale=sig)
        scaling=ampl/norm_peak

        # integrate between bounds
        est = (norm.cdf(bounds[1],loc=locn,scale=sig)-norm.cdf(bounds[0],loc=locn,scale=sig))*ampl*math.sqrt(2*pi*var)
        self.post_pdf_la=norm.pdf(self.param_grid,loc=locn,scale=sig)*ampl*sqrt(2*pi*var)/self.mlike
        
        

        #self.post_mean_la=np.trapz(self.param_grid*self.post_pdf_la, dx=self.delta)
        
        return ampl,locn,sig,est

    def samp_cdf(self):
        """
        Return a single sample from the posterior using the inverse CDF method.
        """
        u = rand()
        i = self.post_cdf.searchsorted(u)  # returns location with val > u
        # Linearly interpolate in the CDF grid.
        du_dpar = (self.post_cdf[i] - self.post_cdf[i-1]) / (self.param_grid[i] - self.param_grid[i-1])
        du = u - self.post_cdf[i-1]
        return self.param_grid[i-1] + du/du_dpar

    def samp_ar(self):
        """
        Return a single sample from the posterior using the accept/reject
        method.
        """
        Q=self.mode_pdf
        u1 = rand()
        u2= random.sample(list(self.param_grid),1)
        while u1*Q>=self.quasi(u2):
            u1 = rand()
            u2= random.sample(list(self.param_grid),1)
            self.n_ar +=1
        #print(u2)
        return u2


    def plot(self, ls='b-', lw=3, alpha=1.):
        """
        Plot the posterior PDF in the current axes.
        """
        plot(self.param_grid, self.post_pdf, ls, lw=lw, alpha=alpha)
