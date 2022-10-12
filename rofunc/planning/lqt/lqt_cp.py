"""
    Linear Quadratic tracker with control primitives applied on a via-point example
"""

from typing import Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
import rofunc as rf


def define_control_primitive(param):
    functions = {
        "PIECEWEISE": rf.primitive.build_phi_piecewise,
        "RBF": rf.primitive.build_phi_rbf,
        "BERNSTEIN": rf.primitive.build_phi_bernstein,
        "FOURIER": rf.primitive.build_phi_fourier
    }
    phi = functions[param["basisName"]](param["nbData"] - 1, param["nbFct"])
    PSI = np.kron(phi, np.identity(param["nbVarPos"]))
    return PSI, phi


def set_dynamical_system(param: Dict):
    nb_var = param["nb_var"]
    A = np.identity(nb_var)
    if param["nbDeriv"] == 2:
        A[:param["nbVarPos"], -param["nbVarPos"]:] = np.identity(param["nbVarPos"]) * param["dt"]

    B = np.zeros((nb_var, param["nbVarPos"]))
    derivatives = [param["dt"], param["dt"] ** 2 / 2][:param["nbDeriv"]]
    for i in range(param["nbDeriv"]):
        B[i * param["nbVarPos"]:(i + 1) * param["nbVarPos"]] = np.identity(param["nbVarPos"]) * derivatives[::-1][i]

    # Build Sx and Su transfer matrices
    Su = np.zeros((nb_var * param["nbData"], param["nbVarPos"] * (param["nbData"] - 1)))  # It's maybe n-1 not sure
    Sx = np.kron(np.ones((param["nbData"], 1)), np.eye(nb_var, nb_var))

    M = B
    for i in range(1, param["nbData"]):
        Sx[i * nb_var:param["nbData"] * nb_var, :] = np.dot(Sx[i * nb_var:param["nbData"] * nb_var, :], A)
        Su[nb_var * i:nb_var * i + M.shape[0], 0:M.shape[1]] = M
        M = np.hstack((np.dot(A, M), B))  # [0,nb_state_var-1]
    return Su, Sx


def get_u_x(param: Dict, start_pose: np.ndarray, muQ: np.ndarray, Q: np.ndarray, R: np.ndarray, Su: np.ndarray,
            Sx: np.ndarray, PSI: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    x0 = start_pose.reshape((param['nb_var'], 1))
    w_hat = np.linalg.inv(PSI.T @ Su.T @ Q @ Su @ PSI + PSI.T @ R @ PSI) @ PSI.T @ Su.T @ Q @ (muQ - Sx @ x0)
    u_hat = PSI @ w_hat
    x_hat = (Sx @ x0 + Su @ u_hat).reshape((-1, param["nb_var"]))
    u_hat = u_hat.reshape((-1, param["nbVarPos"]))
    return u_hat, x_hat


def uni_cp(param: Dict, data: np.ndarray):
    print('\033[1;32m--------{}--------\033[0m'.format('Planning smooth trajectory via LQT (control primitive)'))
    data = data[:, :param['nbVarPos']]

    start_pose = np.zeros((param['nb_var'],), dtype=np.float32)
    start_pose[:param['nbVarPos']] = data[0]

    via_point_pose = data[1:]
    param['nbPoints'] = len(via_point_pose)

    via_point, muQ, Q, R, idx_slices, tl = rf.lqt.get_matrices(param, via_point_pose)
    PSI, phi = define_control_primitive(param)
    Su, Sx = set_dynamical_system(param)
    u_hat, x_hat = get_u_x(param, start_pose, muQ, Q, R, Su, Sx, PSI)

    # vis(param, x_hat, u_hat, muQ, idx_slices, tl, phi)
    rf.lqt.plot_3d_uni([x_hat], muQ, idx_slices)
    # rf.visualab.traj_plot([x_hat[:, :2]])
    return u_hat, x_hat, muQ, idx_slices


def vis(param, x_hat, u_hat, muQ, idx_slices, tl, phi):
    plt.figure()

    plt.title("2D Trajectory")
    plt.axis("off")
    plt.gca().set_aspect('equal', adjustable='box')

    plt.scatter(x_hat[0, 0], x_hat[0, 1], c='black', s=100)

    for slice_t in idx_slices:
        plt.scatter(muQ[slice_t][0], muQ[slice_t][1], c='blue', s=100)

    plt.plot(x_hat[:, 0], x_hat[:, 1], c='black')

    fig, axs = plt.subplots(5, 1)

    axs[0].plot(x_hat[:, 0], c='black')
    axs[0].set_ylabel("$x_1$")
    axs[0].set_xticks([0, param["nbData"]])
    axs[0].set_xticklabels(["0", "T"])
    for t in tl:
        axs[0].scatter(t, x_hat[t, 0], c='blue')

    axs[1].plot(x_hat[:, 1], c='black')
    axs[1].set_ylabel("$x_2$")
    axs[1].set_xticks([0, param["nbData"]])
    axs[1].set_xticklabels(["0", "T"])
    for t in tl:
        axs[1].scatter(t, x_hat[t, 1], c='blue')

    axs[2].plot(u_hat[:, 0], c='black')
    axs[2].set_ylabel("$u_1$")
    axs[2].set_xticks([0, param["nbData"] - 1])
    axs[2].set_xticklabels(["0", "T-1"])

    axs[3].plot(u_hat[:, 1], c='black')
    axs[3].set_ylabel("$u_2$")
    axs[3].set_xticks([0, param["nbData"] - 1])
    axs[3].set_xticklabels(["0", "T-1"])

    axs[4].set_ylabel("$\phi_k$")
    axs[4].set_xticks([0, param["nbData"] - 1])
    axs[4].set_xticklabels(["0", "T-1"])
    for i in range(param["nbFct"]):
        axs[4].plot(phi[:, i])
    axs[4].set_xlabel("$t$")

    plt.show()


if __name__ == '__main__':
    param = {
        "nbData": 200,  # Number of data points
        "nbVarPos": 7,  # Dimension of position data
        "nbDeriv": 2,  # Number of static and dynamic features (2 -> [x,dx])
        "nbFct": 9,  # Number of basis function
        "basisName": "RBF",  # can be PIECEWEISE, RBF, BERNSTEIN, FOURIER
        "dt": 1e-2,  # Time step duration
        "rfactor": 1e-8  # Control cost
    }
    param["nb_var"] = param["nbVarPos"] * param["nbDeriv"]  # Dimension of state vector

    data_raw = np.load('/home/ubuntu/Data/2022_09_09_Taichi/rep3_r.npy')
    data = np.zeros((len(data_raw), 14))
    data[:, :7] = data_raw
    filter_indices = [i for i in range(0, len(data_raw) - 10, 5)]
    filter_indices.append(len(data_raw) - 1)
    via_points = data[filter_indices]

    # via_points = np.array([[2, 5, 0, 0], [3, 1, 0, 0], [3, 6, 0, 0], [4, 2, 0, 0]])

    uni_cp(param, via_points)