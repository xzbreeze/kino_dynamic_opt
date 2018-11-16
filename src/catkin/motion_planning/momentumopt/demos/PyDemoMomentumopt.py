#!/usr/bin/python

'''
 Copyright [2017] Max Planck Society. All rights reserved.

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

from pysolver import *
from pymomentum import *
from pinocchio.utils import *
from pinocchio.robot_wrapper import RobotWrapper
import os, sys, getopt, numpy as np, pinocchio as pin

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.momentumopt.kinoptpy.kinematics_optimizer import KinematicsOptimizer, create_time_vector
from src.momentumexe.motion_execution import MotionExecutor


'Kinematics Interface using Pinocchio'
class PinocchioKinematicsInterface(KinematicsInterface):
    def __init__(self):
        KinematicsInterface.__init__(self)

    def initialize(self, planner_setting):
        urdf = str(os.path.dirname(os.path.abspath(__file__)) + '/quadruped/quadruped.urdf')
        self.robot = RobotWrapper(urdf, root_joint=pin.JointModelFreeFlyer())
        self.eff_names = {0: "BL_END", 1: "FL_END", 2: "BR_END", 3: "FR_END"}

    def updateJacobians(self, kin_state):
        'Generalized joint positions and velocities'
        self.q = np.matrix(np.squeeze(np.asarray(kin_state.robot_posture.generalized_joint_positions()))).transpose()
        self.dq = np.matrix(np.squeeze(np.asarray(kin_state.robot_velocity.generalized_joint_velocities))).transpose()

        'Update of jacobians'
        self.robot.computeJointJacobians(self.q);
        self.robot.framesForwardKinematics(self.q)
        for eff_id in range(0, len(self.eff_names)):
            self.endeffector_jacobians[eff_id] = self.robot.getFrameJacobian(self.robot.model.getFrameId(self.eff_names[eff_id]), pin.ReferenceFrame.WORLD)

        self.robot.centroidalMomentum(self.q, self.dq)
        self.centroidal_momentum_matrix = self.robot.data.Ag

        'Update of kinematics state'
        kin_state.com = self.robot.com(self.q)
        kin_state.lmom = self.robot.data.hg.vector[:3]
        kin_state.amom = self.robot.data.hg.vector[3:]

        for eff_id in range(0, len(self.eff_names)):
            kin_state.endeffector_positions[eff_id] = self.robot.data.oMf[self.robot.model.getFrameId(self.eff_names[eff_id])].translation


class MotionPlanner():

    def __init__(self, cfg_file):
        'define problem configuration'
        self.planner_setting = PlannerSetting()
        self.planner_setting.initialize(cfg_file)

        'define robot initial state'
        self.ini_state = DynamicsState()
        self.ini_state.fillInitialRobotState(cfg_file)

        'define reference dynamic sequence'
        self.kin_sequence = KinematicsSequence()
        self.kin_sequence.resize(self.planner_setting.get(PlannerIntParam_NumTimesteps),
                                 self.planner_setting.get(PlannerIntParam_NumDofs))

        'define terrain description'
        self.terrain_description = TerrainDescription()
        self.terrain_description.loadFromFile(self.planner_setting.get(PlannerStringParam_ConfigFile))

        'define contact plan'
        self.contact_plan = ContactPlanFromFile()
        self.contact_plan.initialize(self.planner_setting)
        self.contact_plan.optimize(self.ini_state, self.terrain_description)


    def optimize_motion(self):
        'optimize motion'
        dyn_optimizer = DynamicsOptimizer()
        dyn_optimizer.initialize(self.planner_setting)
        dyn_optimizer.optimize(self.ini_state, self.contact_plan, self.kin_sequence)

        # print dyn_optimizer.solveTime()
        # print dyn_optimizer.dynamicsSequence().dynamics_states[planner_setting.get(PlannerIntParam_NumTimesteps)-1]
        # print contact_plan.contactSequence().contact_states(0)[0].position

        # 'Kinematics Interface'
        # kin_interface = PinocchioKinematicsInterface()

        'Kinematics Optimizer'
        kin_optimizer = KinematicsOptimizer()
        kin_optimizer.initialize(self.planner_setting)
        kin_optimizer.optimize(self.ini_state, self.contact_plan.contactSequence(), dyn_optimizer.dynamicsSequence())

        optimized_sequence = kin_optimizer.kinematics_sequence

        #print "Second Dynamic Iteration"
        #dyn_optimizer.optimize(ini_state, contact_plan, kin_optimizer.kinematics_sequence, True)

        #print "Second Kinematic Iteration"
        #kin_optimizer.optimize(ini_state, contact_plan.contactSequence(), dyn_optimizer.dynamicsSequence())

        time_vector = create_time_vector(dyn_optimizer.dynamicsSequence())

        return optimized_sequence, time_vector


'Main function for optimization demo'
def main(argv):

    cfg_file = ''
    try:
        opts, args = getopt.getopt(argv,"hi:",["ifile="])
    except getopt.GetoptError:
        print ('PyDemoMomentumopt.py -i <path_to_datafile>')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print ('PyDemoMomentumopt.py -i <path_to_datafile>')
            sys.exit()
        elif opt in ("-i", "--ifile"):
            cfg_file = arg

    print(cfg_file)

    motion_planner = MotionPlanner(cfg_file)
    optimized_sequence, time_vector = motion_planner.optimize_motion()

    optimized_sequence.kinematics_states[15].robot_posture.joint_positions
    optimized_sequence.kinematics_states[15].robot_velocity.joint_velocities

    motion_executor = MotionExecutor(optimized_sequence, time_vector)
    motion_executor.execute_motion()

    print('Done...')

if __name__ == "__main__":
   main(sys.argv[1:])
