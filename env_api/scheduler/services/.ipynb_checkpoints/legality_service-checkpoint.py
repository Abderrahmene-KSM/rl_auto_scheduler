import copy
from typing import List
import numpy as np

from env_api.core.models.optim_cmd import OptimizationCommand
from env_api.core.services.compiling_service import CompilingService
from env_api.core.services.converting_service import ConvertService
from env_api.scheduler.models.action import *
from env_api.scheduler.models.schedule import Schedule


class LegalityService:
    def __init__(self):
        """
        The legality service is responsible to evaluate the legality of tiramisu programs given a specific schedule
        """
        pass
    
    def is_matrix_unimodular(self, matrix):
        det_value = np.linalg.det(matrix)
        return det_value == 1 or det_value == -1

    def is_action_legal(
        self,
        schedule_object: Schedule,
        branches: List[Schedule],
        current_branch: int,
        action: Action,
    ):
        """
        Checks the legality of action
        input :
            - an action that represents an optimization from the 7 types : Parallelization,Skewing,Interchange,Fusion,Reversal,Tiling,Unrolling
        output :
            - legality_check : bool
        """

        branches[current_branch].update_actions_mask(action=action, applied=False)
        # Check first if the iterator(s) level(s) is(are) included in the current iterators
        # If not then the action is illegal by default
        
        if isinstance(action, AddingOne):
            comps= copy.deepcopy(branches[current_branch].comps)
            matrix = np.copy(schedule_object.comps_trans[comps[0]]["matrix"])
            row = schedule_object.comps_trans[comps[0]]["row_number"]
            col = schedule_object.comps_trans[comps[0]]["col_number"]
            action.params.extend([row, col, matrix])
            matrix[row][col] = matrix[row][col] + 1
            unimodularity_check = self.is_matrix_unimodular(matrix)
            if not unimodularity_check:
                print("unimodalirity *****")
                return False
                

        
        if not isinstance(action, NextRow) and not isinstance(action, NextCol): 
            exceeded_iterators = self.check_iterators(
                branches=branches, current_branch=current_branch, action=action
            )
            if exceeded_iterators:
                return False

            # For the cost model we are only allowed to apply 4 affine transformations by branch
            # We verify that every branch doesn't exceed that amount
            legal_affine_trans = self.check_affine_transformations(
                branches=branches, action=action
            )
            if not legal_affine_trans:
                return False

        if isinstance(action, Fusion):
            if current_branch + 1 == len(branches):
                return False
            elif not (
                branches[current_branch].common_it[0]
                == branches[current_branch + 1].common_it[0]
            ):
                return False
            elif not (
                len(branches[current_branch].common_it)
                == len(branches[current_branch + 1].common_it)
            ):
                return False

            current_branch_comp = branches[current_branch].comps[-1]
            next_branch_comp = branches[current_branch + 1].comps[-1]

            level = len(branches[current_branch].common_it) - 1

            action.params.extend([current_branch_comp, next_branch_comp, level])

        # The legality of Skewing is different than the others , we need to get the skewing params from the solver
        # If there are any , this means that skewing is legal , if the solver fails , it means that skewing is illegal
        if isinstance(action, Skewing):
            # check if results of skewing solver exist in the dataset
            schdule_str = ConvertService.build_sched_string(
                schedule_object.schedule_list
            )
            if schdule_str in schedule_object.prog.schedules_solver:
                factors = schedule_object.prog.schedules_solver[schdule_str]

            else:
                if not schedule_object.prog.original_str:
                    # Loading function code lines
                    schedule_object.prog.load_code_lines()
                # Call the skewing solver
                factors = CompilingService.call_skewing_solver(
                    schedule_object=schedule_object,
                    optim_list=schedule_object.schedule_list,
                    action=action,
                    branches=branches,
                )

                # Save the results of skewing solver in the dataset
                schedule_object.prog.schedules_solver[schdule_str] = factors
            if factors == None:
                # The solver fails to find solutions => illegal action
                return False
            else:
                # Adding the factors to the params
                action.params.extend(factors)
                # Assign the requested comps to the action
                optim_command = OptimizationCommand(action)
                # Add the command to the array of schedule
                schedule_object.schedule_list.append(optim_command)
                # Storing the schedule string
                schedule_object.schedule_str = ConvertService.build_sched_string(
                    schedule_object.schedule_list
                )
                return True
        
        # Assign the requested comps to the action
        optim_command = OptimizationCommand(action)
        # Add the command to the array of schedule
        schedule_object.schedule_list.append(optim_command)
        # Building schedule string
        schdule_str = ConvertService.build_sched_string(schedule_object.schedule_list)
        # Check if the action is legal or no to be applied on schedule_object.prog
        # prog.schedules_legality only has data when it is fetched from the offline dataset so no need to compile to get the legality
        if schdule_str in schedule_object.prog.schedules_legality:
            legality_check = int(schedule_object.prog.schedules_legality[schdule_str])
        else:
            # To run the legality we need the original function code to generate legality code
            if not schedule_object.prog.original_str:
                # Loading function code lines
                schedule_object.prog.load_code_lines()
            try:
                legality_check = int(
                    CompilingService.compile_legality(
                        schedule_object=schedule_object,
                        optims_list=schedule_object.schedule_list,
                        branches=branches,
                    )
                )

                # Saving the legality of the new schedule
                schedule_object.prog.schedules_legality[schdule_str] = (
                    legality_check == 1
                )

            except ValueError as e:
                legality_check = 0
                print("Legality error :", e)

        if legality_check != 1:
            # If the action is not legal , remove it from the schedule list
            schedule_object.schedule_list.pop()
            # Rebuild the scedule string after removing the action
            schdule_str = ConvertService.build_sched_string(
                schedule_object.schedule_list
            )
        # Storing the schedule string to use it later
        schedule_object.schedule_str = schdule_str
        return legality_check == 1

    def check_iterators(
        self, branches: List[Schedule], current_branch: int, action: Action
    ):
        params = []
        # Before checking legality from dataset or by compiling , we see if the iterators are included in the common iterators
        if isinstance(action, Unrolling):
            # We look for the last iterator of each computation and save it in the params
            unrolling_factor = action.params[0]

            innermost_iterator = list(
                branches[current_branch].prog.annotations["iterators"].keys()
            )[-1]
            lower_bound = int(
                branches[current_branch].prog.annotations["iterators"][
                    innermost_iterator
                ]["lower_bound"]
            )
            upper_bound = int(
                branches[current_branch].prog.annotations["iterators"][
                    innermost_iterator
                ]["upper_bound"]
            )
            if abs(upper_bound - lower_bound) < unrolling_factor:
                return True

            loop_level = (
                len(branches[current_branch].common_it)
                - 1
                + branches[current_branch].additional_loops
            )
            action.params = copy.deepcopy([loop_level, unrolling_factor])
            action.comps = copy.deepcopy(branches[current_branch].comps)
            return False
        else:
            num_iter = branches[current_branch].common_it.__len__()
            if isinstance(action, Tiling):
                # First we verify if the tiling size is bigger than the loops extent
                # TODO : remove this strategy later
                tiling_size = max(action.params)
                for iterator in branches[current_branch].prog.annotations["iterators"]:
                    lower_bound = int(
                        branches[current_branch].prog.annotations["iterators"][
                            iterator
                        ]["lower_bound"]
                    )
                    upper_bound = int(
                        branches[current_branch].prog.annotations["iterators"][
                            iterator
                        ]["upper_bound"]
                    )
                    if abs(upper_bound - lower_bound) < tiling_size:
                        return True
                # Becuase the second half of action.params contains tiling size, so we need only the first half of the vector
                params = action.params[: len(action.params) // 2]
            elif isinstance(action, AddingOne):
                # exclude the matrix from parameters
                params = action.params[:-1]
            else:
                params = action.params
            # Checking if the big param is smaller than the number of existing iterators
            if params[-1] >= num_iter:
                return True

        # We have the current branch
        concerned_iterators = [branches[current_branch].common_it[it] for it in params]
        concerned_comps = []
        match len(concerned_iterators):
            case 1:
                for branch in branches:
                    if concerned_iterators[0] in branch.common_it:
                        concerned_comps.extend(branch.comps)
            case 2:
                for branch in branches:
                    if concerned_iterators[0] in branch.common_it:
                        if concerned_iterators[1] in branch.common_it:
                            concerned_comps.extend(branch.comps)
                        else:
                            # If for some branch , we have the parent iterator shared with current branch but
                            # the child is different , this means that only the parent is shared and the children are different
                            return True
            case 3:
                for branch in branches:
                    if concerned_iterators[0] in branch.common_it:
                        if concerned_iterators[1] in branch.common_it:
                            if concerned_iterators[2] in branch.common_it:
                                concerned_comps.extend(branch.comps)
                            else:
                                return True
                        else:
                            return True
        action.comps = copy.deepcopy(concerned_comps)
        return False

    def check_affine_transformations(self, branches: List[Schedule], action: Action):
        if isinstance(action, AffineAction):
            for branch in branches:
                for comp in action.comps:
                    if comp in branch.comps and branch.transformed == 4:
                        return False
        return True
