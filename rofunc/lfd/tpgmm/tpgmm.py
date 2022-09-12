import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pbdlib as pbd
import utils


def get_dx(demos_x):
    demos_dx = []
    for i in range(len(demos_x)):
        demo_dx = []
        for j in range(len(demos_x[i])):
            if 0 < j < len(demos_x[i]) - 1:
                dx = (demos_x[i][j + 1] - demos_x[i][j - 1]) / 2
            elif j == len(demos_x[i]) - 1:
                dx = demos_x[i][j] - demos_x[i][j - 1]
            else:
                dx = demos_x[i][j + 1] - demos_x[i][j]
            dx = dx / 0.01
            demo_dx.append(dx)
        demos_dx.append(np.array(demo_dx))
    return demos_dx


def get_A_b(demos_x):
    demos_b = []
    demos_A = []
    for i in range(len(demos_x)):
        demos_b.append(np.tile(np.vstack([demos_x[i][0], demos_x[i][-1], ]), (len(demos_x[i]), 1, 1)))
        demos_A.append(np.tile([[[1., 0.], [-0., -1.]], [[1., 0.], [-0., -1.]]], (len(demos_x[i]), 1, 1, 1)))
    demos_A_xdx = [np.kron(np.eye(len(demos_x[0][0])), d) for d in demos_A]
    demos_b_xdx = [np.concatenate([d, np.zeros(d.shape)], axis=-1) for d in demos_b]

    return demos_A, demos_b, demos_A_xdx, demos_b_xdx


def get_related_matrix(demos_x):
    demos_dx = get_dx(demos_x)
    demos_xdx = [np.hstack([_x, _dx]) for _x, _dx in
                 zip(demos_x, demos_dx)]  # Position and velocity (num_of_points, 14)
    demos_A, demos_b, demos_A_xdx, demos_b_xdx = get_A_b(demos_x)
    demos_xdx_f = [np.einsum('taji,taj->tai', _A, _x[:, None] - _b) for _x, _A, _b in
                   zip(demos_xdx, demos_A_xdx, demos_b_xdx)]
    demos_xdx_augm = [d.reshape(-1, len(demos_xdx[0][0]) * 2) for d in
                      demos_xdx_f]  # (num_of_points, 28): 0~13 pos-vel in coord 1, 14~27 pos-vel in coord 2
    return demos_xdx, demos_A_xdx, demos_b_xdx, demos_xdx_f, demos_xdx_augm


def HMM_learning(demos_xdx_f, demos_xdx_augm, plot=False):
    model = pbd.HMM(nb_states=4)
    model.init_hmm_kbins(demos_xdx_augm)  # initializing model

    model.em(demos_xdx_augm, reg=1e-3)

    # plotting
    if plot:
        if int(len(demos_xdx_f[0][0, 0]) / 2) == 2:
            utils.hmm_plot(demos_xdx_f, model)
        elif int(len(demos_xdx_f[0][0, 0]) / 2) > 2:
            utils.hmm_plot_3d(demos_xdx_f, model)
        else:
            raise Exception('Dimension is less than 2, cannot plot')
    return model


def poe(model, demos_A_xdx, demos_b_xdx, demos_x, demo_idx, plot=False):
    # get transformation for given demonstration.
    # We use the transformation of the first timestep as they are constant
    A, b = demos_A_xdx[demo_idx][0], demos_b_xdx[demo_idx][0]
    # transformed model for coordinate system 1
    mod1 = model.marginal_model(slice(0, len(b[0]))).lintrans(A[0], b[0])
    # transformed model for coordinate system 2
    mod2 = model.marginal_model(slice(len(b[0]), len(b[0]) * 2)).lintrans(A[1], b[1])
    # product
    prod = mod1 * mod2

    if plot:
        if len(demos_x[0, 0]) == 2:
            utils.poe_plot(model, mod1, mod2, prod, demos_x, demo_idx)
        elif len(demos_x[0, 0]) > 2:
            utils.poe_plot_3d(model, mod1, mod2, prod, demos_x, demo_idx)
        else:
            raise Exception('Dimension is less than 2, cannot plot')
    return prod


def generate(model, prod, demos_x, demos_xdx, demos_xdx_augm, demo_idx, plot=False):
    # get the most probable sequence of state for this demonstration
    sq = model.viterbi(demos_xdx_augm[demo_idx])

    # solving LQR with Product of Gaussian, see notebook on LQR
    lqr = pbd.PoGLQR(nb_dim=7, dt=0.01, horizon=demos_xdx[demo_idx].shape[0])
    lqr.mvn_xi = prod.concatenate_gaussian(sq)  # augmented version of gaussian
    lqr.mvn_u = -4
    lqr.x0 = demos_xdx[demo_idx][0]

    xi = lqr.seq_xi
    if plot:
        if len(demos_x[0, 0]) == 2:
            utils.generate_plot(xi, prod, demos_x, demo_idx)
        elif len(demos_x[0, 0]) > 2:
            utils.generate_plot_3d(xi, prod, demos_x, demo_idx)
        else:
            raise Exception('Dimension is less than 2, cannot plot')
    return xi


def uni(demos_x, show_demo_idx, plot=False):
    demos_xdx, demos_A_xdx, demos_b_xdx, demos_xdx_f, demos_xdx_augm = get_related_matrix(demos_x)
    model = HMM_learning(demos_xdx_f, demos_xdx_augm, plot=plot)
    prod = poe(model, demos_A_xdx, demos_b_xdx, demos_x, show_demo_idx, plot=plot)
    gen = generate(model, prod, demos_x, demos_xdx, demos_xdx_augm, show_demo_idx, plot=plot)

    if plot:
        plt.figure()
        plt.plot(gen[:, 0], gen[:, 1])
        plt.show()
    return gen


def bi(demos_left_x, demos_right_x, show_demo_idx, plot=False):
    demos_left_xdx, demos_left_A_xdx, demos_left_b_xdx, demos_left_xdx_f, demos_left_xdx_augm = get_related_matrix(
        demos_left_x)
    demos_right_xdx, demos_right_A_xdx, demos_right_b_xdx, demos_right_xdx_f, demos_right_xdx_augm = get_related_matrix(
        demos_right_x)

    model_l = HMM_learning(demos_left_xdx_f, demos_left_xdx_augm, plot=plot)
    model_r = HMM_learning(demos_right_xdx_f, demos_right_xdx_augm, plot=plot)

    prod_l = poe(model_l, demos_left_A_xdx, demos_left_b_xdx, demos_left_x, show_demo_idx, plot=plot)
    prod_r = poe(model_r, demos_right_A_xdx, demos_right_b_xdx, demos_right_x, show_demo_idx, plot=plot)

    gen_l = generate(model_l, prod_l, demos_left_x, demos_left_xdx, demos_left_xdx_augm, show_demo_idx, plot=plot)
    gen_r = generate(model_r, prod_r, demos_right_x, demos_right_xdx, demos_right_xdx_augm, show_demo_idx, plot=plot)

    if plot:
        plt.figure()
        plt.plot(gen_l[:, 0], gen_l[:, 1])
        plt.plot(gen_r[:, 0], gen_r[:, 1])
        plt.show()
    return gen_l, gen_r


if __name__ == '__main__':
    import rofunc as rf

    # Uni
    # demo_points = np.array([[[0, 0], [-1, 8], [4, 3], [2, 1], [4, 3]],
    #                         [[0, -2], [-1, 7], [3, 2.5], [2, 1.6], [4, 3]],
    #                         [[0, -1], [-1, 8], [4, 5.2], [2, 1.1], [4, 3.5]]])
    # demos_x = rf.utils.bezier.multi_bezier_demos(demo_points)  # (3, 50, 2): 3 demos, each has 50 points
    # rf.tpgmm.uni(demos_x, show_demo_idx=2, plot=True)

    # Bi
    # left_demo_points = np.array([[[0, 0], [-1, 8], [4, 3], [2, 1], [4, 3]],
    #                              [[0, -2], [-1, 7], [3, 2.5], [2, 1.6], [4, 3]],
    #                              [[0, -1], [-1, 8], [4, 5.2], [2, 1.1], [4, 3.5]]])
    # right_demo_points = np.array([[[8, 8], [7, 1], [4, 3], [6, 8], [4, 3]],
    #                               [[8, 7], [7, 1], [3, 3], [6, 6], [4, 3]],
    #                               [[8, 8], [7, 1], [4, 5], [6, 8], [4, 3.5]]])
    # demos_left_x = rf.utils.bezier.multi_bezier_demos(left_demo_points)  # (3, 50, 2): 3 demos, each has 50 points
    # demos_right_x = rf.utils.bezier.multi_bezier_demos(right_demo_points)
    # bi(demos_left_x, demos_right_x, show_demo_idx=2, plot=False)

    # Uni_3d
    # demo_points = np.array([[[0, 0, 1], [-1, 8, 1], [4, 3, 2], [2, 1, 2], [4, 3, 2]],
    #                         [[0, -2, 1], [-1, 7, 1], [3, 2.5, 2], [2, 1.6, 2], [4, 3, 2]],
    #                         [[0, -1, 1], [-1, 8, 1], [4, 5.2, 2], [2, 1.1, 2], [4, 3.5, 2]]])
    # demos_x = rf.utils.bezier.multi_bezier_demos(demo_points)  # (3, 50, 2): 3 demos, each has 50 points
    raw_demo = np.load('/home/ubuntu/Data/2022_09_09_Taichi/xsens_mvnx/010-058/LeftHand.npy')
    raw_demo = np.expand_dims(raw_demo, axis=0)
    demos_x = np.vstack((raw_demo[:, 82:232, :], raw_demo[:, 233:383, :], raw_demo[:, 376:526, :]))

    gen = uni(demos_x, show_demo_idx=2, plot=True)
    print()