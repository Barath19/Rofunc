import os.path
from typing import List

import numpy as np
from isaacgym import gymapi
from isaacgym import gymtorch
from isaacgym import gymutil
import torch
import matplotlib.pyplot as plt
from PIL import Image as Im

from rofunc.simulator.base.base_sim import init_sim, init_env, init_attractor, get_num_bodies, get_robot_state
from rofunc.utils.logger.beauty_logger import beauty_print


def update_robot(traj, gym, envs, attractor_handles, axes_geom, sphere_geom, viewer, num_envs, index, t):
    for i in range(num_envs):
        # Update attractor target from current franka state
        attractor_properties = gym.get_attractor_properties(envs[i], attractor_handles[i])
        pose = attractor_properties.target
        # pose.p: (x, y, z), pose.r: (w, x, y, z)
        pose.p.x = traj[index, 0]
        pose.p.y = traj[index, 2]
        pose.p.z = traj[index, 1]
        pose.r.w = traj[index, 6]
        pose.r.x = traj[index, 3]
        pose.r.y = traj[index, 5]
        pose.r.z = traj[index, 4]
        gym.set_attractor_target(envs[i], attractor_handles[i], pose)

        # Draw axes and sphere at attractor location
        gymutil.draw_lines(axes_geom, gym, viewer, envs[i], pose)
        gymutil.draw_lines(sphere_geom, gym, viewer, envs[i], pose)


def setup_curi(args, asset_root, num_envs, for_test):
    # Initial gym and sim
    gym, sim_params, sim, viewer = init_sim(args, for_test=for_test)

    # Load CURI asset and set the env
    if asset_root is None:
        from rofunc.utils.file import get_rofunc_path
        asset_root = os.path.join(get_rofunc_path(), "simulator/assets")
    asset_file = "urdf/curi/urdf/curi_isaacgym.urdf"
    envs, curi_handles = init_env(gym, sim, asset_root, asset_file, num_envs=num_envs, fix_base_link=False)

    num_bodies = get_num_bodies(gym, sim, asset_root, asset_file)

    # get joint limits and ranges for CURI
    curi_dof_props = gym.get_actor_dof_properties(envs[0], curi_handles[0])
    curi_lower_limits = curi_dof_props['lower']
    curi_upper_limits = curi_dof_props['upper']
    curi_mids = 0.5 * (curi_upper_limits + curi_lower_limits)
    curi_num_dofs = len(curi_dof_props)

    for i in range(len(envs)):
        # Set updated stiffness and damping properties
        gym.set_actor_dof_properties(envs[i], curi_handles[i], curi_dof_props)

        # Set ranka pose so that each joint is in the middle of its actuation range
        curi_dof_states = gym.get_actor_dof_states(envs[i], curi_handles[i], gymapi.STATE_NONE)
        for j in range(curi_num_dofs):
            curi_dof_states['pos'][j] = curi_mids[j]
        gym.set_actor_dof_states(envs[i], curi_handles[i], curi_dof_states, gymapi.STATE_POS)
    return gym, sim_params, sim, viewer, envs, curi_handles, num_bodies


def setup_attractor(gym, envs, viewer, curi_handles, traj, attracted_joints, for_test):
    if attracted_joints is None:
        attracted_joints = ["panda_left_hand", "panda_right_hand"]
    else:
        assert isinstance(attracted_joints, list) and len(attracted_joints) > 0, "The attracted joints should be a list"
    assert len(attracted_joints) == len(traj), "The number of trajectories should be the same as the number of joints"

    attractor_handles, axes_geoms, sphere_geoms = [], [], []
    for i in range(len(attracted_joints)):
        attractor_handle, axes_geom, sphere_geom = init_attractor(gym, envs, viewer, curi_handles, attracted_joints[i],
                                                                  for_test=for_test)
        attractor_handles.append(attractor_handle)
        axes_geoms.append(axes_geom)
        sphere_geoms.append(sphere_geom)
    return attracted_joints, attractor_handles, axes_geoms, sphere_geoms


def show(args, asset_root=None):
    """

    Args:
        args:
        asset_root: the location of `assets` folder, e.g., /home/ubuntu/anaconda3/envs/plast/lib/python3.7/site-packages/rofunc/simulator/assets

    Returns:

    """
    print('\033[1;32m--------{}--------\033[0m'.format('Show the CURI simulator in the interactive mode'))

    # Initial gym and sim
    gym, sim_params, sim, viewer = init_sim(args)

    # Load CURI asset and set the env
    if asset_root is None:
        from rofunc.utils.file import get_rofunc_path
        asset_root = os.path.join(get_rofunc_path(), "simulator/assets")
    asset_file = "urdf/curi/urdf/curi_isaacgym.urdf"
    envs, handles = init_env(gym, sim, asset_root, asset_file, num_envs=5, spacing=3.0, fix_base_link=False)

    # Camera Sensor
    camera_props = gymapi.CameraProperties()
    camera_props.width = 1280
    camera_props.height = 1280
    camera_props.enable_tensors = True
    camera_handle = gym.create_camera_sensor(envs[0], camera_props)

    transform = gymapi.Transform()
    transform.p = gymapi.Vec3(1, 1, 1)
    transform.r = gymapi.Quat.from_axis_angle(gymapi.Vec3(0, 1, 0), np.radians(45.0))
    gym.set_camera_transform(camera_handle, envs[0], transform)
    debug_fig = plt.figure("debug")

    while not gym.query_viewer_has_closed(viewer):
        # Step the physics
        gym.simulate(sim)
        gym.fetch_results(sim, True)

        # Step rendering
        gym.step_graphics(sim)

        # digest image
        gym.render_all_camera_sensors(sim)
        gym.start_access_image_tensors(sim)

        camera_tensor = gym.get_camera_image_gpu_tensor(sim, envs[0], camera_handle, gymapi.IMAGE_COLOR)
        torch_camera_tensor = gymtorch.wrap_tensor(camera_tensor)
        cam_img = torch_camera_tensor.cpu().numpy()
        cam_img = Im.fromarray(cam_img)
        plt.imshow(cam_img)
        plt.pause(1e-9)
        debug_fig.clf()

        gym.end_access_image_tensors(sim)

        gym.draw_viewer(viewer, sim, False)
        gym.sync_frame_time(sim)

    print("Done")

    gym.destroy_viewer(viewer)
    gym.destroy_sim(sim)


def run_traj(args, traj, attracted_joint="panda_right_hand", asset_root=None, update_freq=0.001):
    """
    TODO: Refine the code to make it more general
    Args:
        args:
        traj:
        attracted_joint:
        asset_root: the location of `assets` folder, e.g., /home/ubuntu/anaconda3/envs/plast/lib/python3.7/site-packages/rofunc/simulator/assets
        update_freq:

    Returns:

    """
    print('\033[1;32m--------{}--------\033[0m'.format('Execute trajectory with the CURI simulator'))

    # Initial gym and sim
    gym, sim_params, sim, viewer = init_sim(args)

    # Load CURI asset and set the env
    if asset_root is None:
        from rofunc.utils.file import get_rofunc_path
        asset_root = os.path.join(get_rofunc_path(), "simulator/assets")
    asset_file = "urdf/curi/urdf/curi_isaacgym.urdf"
    envs, curi_handles = init_env(gym, sim, asset_root, asset_file, num_envs=1, fix_base_link=False)

    # Create the attractor
    attractor_handles, axes_geom, sphere_geom = init_attractor(gym, envs, viewer, curi_handles, attracted_joint)

    # get joint limits and ranges for Franka
    curi_dof_props = gym.get_actor_dof_properties(envs[0], curi_handles[0])
    curi_lower_limits = curi_dof_props['lower']
    curi_upper_limits = curi_dof_props['upper']
    curi_mids = 0.5 * (curi_upper_limits + curi_lower_limits)
    curi_num_dofs = len(curi_dof_props)

    for i in range(len(envs)):
        # Set updated stiffness and damping properties
        gym.set_actor_dof_properties(envs[i], curi_handles[i], curi_dof_props)

        # Set ranka pose so that each joint is in the middle of its actuation range
        curi_dof_states = gym.get_actor_dof_states(envs[i], curi_handles[i], gymapi.STATE_NONE)
        for j in range(curi_num_dofs):
            curi_dof_states['pos'][j] = curi_mids[j]
        gym.set_actor_dof_states(envs[i], curi_handles[i], curi_dof_states, gymapi.STATE_POS)

    # Time to wait in seconds before moving robot
    next_curi_update_time = 1

    index = 0
    while not gym.query_viewer_has_closed(viewer):
        # Every 0.01 seconds the pose of the attractor is updated
        t = gym.get_sim_time(sim)
        if t >= next_curi_update_time:
            gym.clear_lines(viewer)
            update_robot(traj, gym, envs, attractor_handles, axes_geom, sphere_geom, viewer, len(envs), index, t)
            next_curi_update_time += update_freq
            index += 1
            if index >= len(traj):
                index = 0

        # Step the physics
        gym.simulate(sim)
        gym.fetch_results(sim, True)

        # Step rendering
        gym.step_graphics(sim)
        gym.draw_viewer(viewer, sim, False)
        gym.sync_frame_time(sim)

    print("Done")

    gym.destroy_viewer(viewer)
    gym.destroy_sim(sim)


def run_traj_multi_joints(args, traj: List, attracted_joints: List = None, asset_root=None, update_freq=0.001,
                          num_envs=1, for_test=False):
    """
    Run the trajectory with multiple joints, the default is to run the trajectory with the left and right hand of the
    CURI robot.
    Args:
        args: the arguments for the Isaac Gym simulator
        traj: a list of trajectories, each trajectory is a numpy array of shape (N, 7)
        attracted_joints: [list], e.g. ["panda_left_hand", "panda_right_hand"]
        asset_root: the location of `assets` folder, e.g., /home/ubuntu/anaconda3/envs/plast/lib/python3.7/site-packages/rofunc/simulator/assets
        update_freq: the frequency of updating the robot pose
        num_envs: the number of environments
        for_test: if True, the simulator will be shown in the headless mode
    """
    assert isinstance(traj, list) and len(traj) > 0, "The trajectory should be a list of numpy arrays"

    beauty_print('Execute multi-joint trajectory with the CURI simulator')

    # Initial gym, sim and envs
    gym, sim_params, sim, viewer, envs, curi_handles, num_bodies = setup_curi(args, asset_root, num_envs, for_test)

    # Create the attractor
    attracted_joints, attractor_handles, axes_geoms, sphere_geoms = setup_attractor(gym, envs, viewer, curi_handles,
                                                                                    traj, attracted_joints, for_test)

    # Time to wait in seconds before moving robot
    next_curi_update_time = 1
    index = 0
    while not gym.query_viewer_has_closed(viewer):
        # Every 0.01 seconds the pose of the attractor is updated
        t = gym.get_sim_time(sim)
        if t >= next_curi_update_time:
            gym.clear_lines(viewer)
            for i in range(len(attracted_joints)):
                update_robot(traj[i], gym, envs, attractor_handles[i], axes_geoms[i], sphere_geoms[i], viewer,
                             len(envs), index, t)
            next_curi_update_time += update_freq
            index += 1
            if index >= len(traj[i]):
                index = 0

        # Step the physics
        gym.simulate(sim)
        gym.fetch_results(sim, True)

        # Step rendering
        if not for_test:
            gym.step_graphics(sim)
            gym.draw_viewer(viewer, sim, False)
            gym.sync_frame_time(sim)

    print("Done")

    gym.destroy_viewer(viewer)
    gym.destroy_sim(sim)


def run_traj_multi_joints_with_interference(args, traj: List, intf_index: List, intf_mode: str,
                                            intf_forces: torch.Tensor = None, intf_torques: torch.Tensor = None,
                                            intf_joints: List = None, intf_efforts: np.ndarray = None,
                                            attracted_joints: List = None, asset_root=None,
                                            update_freq=0.001, num_envs=1, save_name=None, for_test=False):
    """
    Run the trajectory with multiple joints with interference, the default is to run the trajectory with the left and
    right hand of the CURI robot.
    Args:
        args: the arguments for the Isaac Gym simulator
        traj: a list of trajectories, each trajectory is a numpy array of shape (N, 7)
        intf_index: a list of the timing indices of the interference occurs
        intf_mode: the mode of the interference, ["actor_dof_efforts", "body_forces", "body_force_at_pos"]
        intf_forces: a tensor of shape (num_envs, num_bodies, 3), the interference forces applied to the bodies
        intf_torques: a tensor of shape (num_envs, num_bodies, 3), the interference torques applied to the bodies
        intf_joints: [list], e.g. ["panda_left_hand"]
        intf_efforts: array containing the efforts for all degrees of freedom of the actor.
        attracted_joints: [list], e.g. ["panda_left_hand", "panda_right_hand"]
        asset_root: the location of `assets` folder, e.g., /home/ubuntu/anaconda3/envs/plast/lib/python3.7/site-packages/rofunc/simulator/assets
        update_freq: the frequency of updating the robot pose
        num_envs: the number of environments
        for_test: if True, the simulator will be shown in the headless mode
    """
    assert isinstance(traj, list) and len(traj) > 0, "The trajectory should be a list of numpy arrays"
    assert intf_mode in ["actor_dof_efforts", "body_forces", "body_force_at_pos"], \
        "The interference mode should be one of ['actor_dof_efforts', 'body_forces', 'body_force_at_pos']"

    beauty_print('Execute multi-joint trajectory with interference with the CURI simulator')

    # Initial gym, sim and envs
    gym, sim_params, sim, viewer, envs, curi_handles, num_bodies = setup_curi(args, asset_root, num_envs, for_test)

    device = args.sim_device if args.use_gpu_pipeline else 'cpu'
    if intf_forces is not None:
        assert intf_forces.shape == torch.Size([num_envs, num_bodies,
                                                3]), "The shape of forces is not correct, it should be (num_envs, num_bodies, 3)"
        intf_forces = intf_forces.to(device)
    if intf_torques is not None:
        assert intf_torques.shape == torch.Size([num_envs, num_bodies,
                                                 3]), "The shape of torques is not correct, it should be (num_envs, num_bodies, 3)"
        intf_torques = intf_torques.to(device)

    # Create the attractor
    attracted_joints, attractor_handles, axes_geoms, sphere_geoms = setup_attractor(gym, envs, viewer, curi_handles,
                                                                                    traj, attracted_joints, for_test)

    # Time to wait in seconds before moving robot
    next_curi_update_time = 1
    index = 0
    states = []
    while not gym.query_viewer_has_closed(viewer):
        # Every 0.01 seconds the pose of the attractor is updated
        t = gym.get_sim_time(sim)
        if t >= next_curi_update_time:
            gym.clear_lines(viewer)
            for i in range(len(attracted_joints)):
                update_robot(traj[i], gym, envs, attractor_handles[i], axes_geoms[i], sphere_geoms[i], viewer,
                             len(envs), index, t)
            next_curi_update_time += update_freq
            index += 1
            if index >= len(traj[0]):
                index = 0

            # Create the interference
            if index in intf_index:
                if intf_mode == "actor_dof_efforts":
                    # gym.set_dof_actuation_force_tensor(sim, gymtorch.unwrap_tensor(intf_efforts))
                    for i in range(len(envs)):
                        gym.apply_actor_dof_efforts(envs[i], curi_handles[i], intf_efforts)
                elif intf_mode == "body_forces":
                    # set intf_forces and intf_torques for the specific bodies
                    gym.apply_rigid_body_force_tensors(sim, gymtorch.unwrap_tensor(intf_forces),
                                                       gymtorch.unwrap_tensor(intf_torques), gymapi.ENV_SPACE)

            # Get current robot state
            state = get_robot_state(gym, sim, envs, curi_handles, mode='dof_state')
            states.append(np.array(state))

        # Step the physics
        gym.simulate(sim)
        gym.fetch_results(sim, True)

        # Step rendering
        if not for_test:
            gym.step_graphics(sim)
            gym.draw_viewer(viewer, sim, False)
            gym.sync_frame_time(sim)

    print("Done")

    with open('{}.npy'.format(save_name), 'wb') as f:
        np.save(f, np.array(states))
    beauty_print('{}.npy saved'.format(save_name), 2)

    gym.destroy_viewer(viewer)
    gym.destroy_sim(sim)
