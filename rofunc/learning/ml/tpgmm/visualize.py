import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import rofunc as rf

color_list = ['steelblue', 'orangered', 'green', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']


def hmm_plot(nb_dim, demos_xdx_f, model):
    if nb_dim == 2:
        fig = hmm_plot2d(demos_xdx_f, model)
    elif nb_dim > 2:
        fig = hmm_plot_3d(demos_xdx_f, model, scale=0.1)
    else:
        raise Exception('Dimension is less than 2, cannot plot')
    return fig


def poe_plot(nb_dim, mod_list, prod, demos_x, show_demo_idx):
    if nb_dim == 2:
        fig = poe_plot2d(mod_list, prod, demos_x, show_demo_idx)
    elif nb_dim > 2:
        fig = poe_plot_3d(mod_list, prod, demos_x, show_demo_idx)
    else:
        raise Exception('Dimension is less than 2, cannot plot')
    return fig


def hmm_plot2d(demos_xdx_f, model):
    P = len(demos_xdx_f[0][0])
    fig, ax = plt.subplots(ncols=P, nrows=1)
    fig.set_size_inches(4 * P, 6)

    for p in range(P):
        ax[p].set_title('pos - coord. %d' % (p + 1))
        for d in demos_xdx_f:
            ax[p].plot(d[:, p, 0], d[:, p, 1])
        rf.visualab.gmm_plot(model.mu, model.sigma, ax=ax[p], dim=[4 * p, 4 * p + 1], color=color_list[p], alpha=0.1)

    plt.tight_layout()
    return fig


def hmm_plot_3d(demos_xdx_f, model, scale=1):
    P = len(demos_xdx_f[0][0])
    nb_dim_deriv = len(demos_xdx_f[0][0][0])
    fig = plt.figure(figsize=(4, 4))
    fig.set_size_inches((4 * P, 6))

    for p in range(P):
        ax = fig.add_subplot(1, P, p + 1, projection='3d', fc='white')
        ax.set_title('pos - coord. %d' % (p + 1))
        for d in demos_xdx_f:
            ax.plot(d[:, p, 0], d[:, p, 1], d[:, p, 2])
        rf.visualab.gmm_plot(model.mu, model.sigma, ax=ax,
                             dim=[nb_dim_deriv * p, nb_dim_deriv * p + 1, nb_dim_deriv * p + 2], color=color_list[p],
                             scale=scale, alpha=0.1)
        rf.visualab.set_axis(ax)
    return fig


def poe_plot2d(mod_list, prod, demos_x, demo_idx):
    P = len(mod_list)
    fig, ax = plt.subplots(ncols=P + 1, nrows=1)
    fig.set_size_inches((4 * (P + 1), 6))
    for i in ax:
        i.set_aspect('equal')

    for p in range(P):
        ax[p].set_title('model %d' % (p + 1))
        rf.visualab.gmm_plot(mod_list[p].mu, mod_list[p].sigma, swap=True, ax=ax[p], dim=[0, 1], color=color_list[p],
                             alpha=0.3)

    ax[P].set_title('tranformed models and product')
    for p in range(P):
        rf.visualab.gmm_plot(mod_list[p].mu, mod_list[p].sigma, swap=True, ax=ax[P], dim=[0, 1], color=color_list[p],
                             alpha=0.3)
    rf.visualab.gmm_plot(prod.mu, prod.sigma, swap=True, ax=ax[P], dim=[0, 1], color='gold', alpha=0.3)
    ax[P].plot(demos_x[demo_idx][:, 0], demos_x[demo_idx][:, 1], color="b")

    patches = [mpatches.Patch(color='steelblue', label='transformed model 1'),
               mpatches.Patch(color='orangered', label='transformed model 2'),
               mpatches.Patch(color='gold', label='product')]

    plt.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
    return fig


def poe_plot_3d(mod_list, prod, demos_x, demo_idx):
    P = len(mod_list)
    fig = plt.figure(figsize=(4, 4))
    fig.set_size_inches((4 * (P + 1), 6))

    for p in range(P):
        ax = fig.add_subplot(1, P + 1, p + 1, projection='3d', fc='white')
        ax.set_title('model %d' % (p + 1))
        rf.visualab.gmm_plot(mod_list[p].mu, mod_list[p].sigma, swap=True, ax=ax, dim=[0, 1, 2], color=color_list[p],
                             alpha=0.05)
        rf.visualab.set_axis(ax)

    ax = fig.add_subplot(1, 4, 4, projection='3d', fc='white')
    ax.set_title('transformed models and product')
    for p in range(P):
        rf.visualab.gmm_plot(mod_list[p].mu, mod_list[p].sigma, swap=True, ax=ax, dim=[0, 1, 2], color=color_list[p],
                             alpha=0.05)
    rf.visualab.gmm_plot(prod.mu, prod.sigma, swap=True, ax=ax, dim=[0, 1, 2], color='gold', alpha=0.05)
    ax.plot(demos_x[demo_idx][:, 0], demos_x[demo_idx][:, 1], demos_x[demo_idx][:, 2], color="b")
    rf.visualab.set_axis(ax)

    patches = [mpatches.Patch(color='steelblue', label='transformed model 1'),
               mpatches.Patch(color='orangered', label='transformed model 2'),
               mpatches.Patch(color='gold', label='product')]

    plt.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
    return fig


def generate_plot(xi, prod, demos_x, demo_idx):
    fig = plt.figure()

    plt.title('Trajectory reproduction')
    rf.visualab.gmm_plot(prod.mu, prod.sigma, swap=True, dim=[0, 1], color='gold', alpha=0.5)
    plt.plot(xi[:, 0], xi[:, 1], color='r', lw=2, label='generated line')
    plt.plot(demos_x[demo_idx][:, 0], demos_x[demo_idx][:, 1], 'k--', lw=2, label='demo line')
    plt.axis('equal')
    plt.legend()
    return fig


def generate_plot_3d(xi, prod, demos_x, demo_idx, scale=0.01, plot_gmm=False, plot_ori=True):
    fig = plt.figure(figsize=(4, 4))
    ax = fig.add_subplot(111, projection='3d', fc='white')

    ax.set_title('Trajectory reproduction')
    ax.plot(xi[:, 0], xi[:, 1], xi[:, 2], color='r', lw=2, label='generated line')
    if plot_gmm:
        rf.visualab.gmm_plot(prod.mu, prod.sigma, dim=[0, 1, 2], color='gold', scale=0.01, ax=ax)
    ax.plot(demos_x[demo_idx][:, 0], demos_x[demo_idx][:, 1], demos_x[demo_idx][:, 2], 'k--', lw=2, label='demo line')
    rf.visualab.set_axis(ax)
    plt.legend()

    if plot_ori and xi.shape[1] == 7:
        t = np.arange(len(xi))
        plt.figure()
        plt.subplot(2, 2, 1)
        plt.plot(t, xi[:, 3], color='r', lw=2, label='generated line')
        plt.plot(np.arange(len(demos_x[demo_idx][:, 3])), demos_x[demo_idx][:, 3], 'k--', lw=2, label='demo line')
        plt.title('w-t')

        plt.subplot(2, 2, 2)
        plt.plot(t, xi[:, 4], color='r', lw=2, label='generated line')
        plt.plot(np.arange(len(demos_x[demo_idx][:, 4])), demos_x[demo_idx][:, 4], 'k--', lw=2, label='demo line')
        plt.title('x-t')

        plt.subplot(2, 2, 3)
        plt.plot(t, xi[:, 5], color='r', lw=2, label='generated line')
        plt.plot(np.arange(len(demos_x[demo_idx][:, 5])), demos_x[demo_idx][:, 5], 'k--', lw=2, label='demo line')
        plt.title('y-t')

        plt.subplot(2, 2, 4)
        plt.plot(t, xi[:, 6], color='r', lw=2, label='generated line')
        plt.plot(np.arange(len(demos_x[demo_idx][:, 6])), demos_x[demo_idx][:, 6], 'k--', lw=2, label='demo line')
        plt.title('z-t')
    return fig
