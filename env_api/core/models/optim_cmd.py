from env_api.scheduler.models.action import *
import numpy as np

def numpy_array_to_string(arr):
    # Convert the NumPy array to a list of lists
    nested_lists = arr.tolist()

    # Convert each inner list to a string and join them with ', '
    inner_strings = [', '.join(map(str, inner)) for inner in nested_lists]

    # Enclose each inner string in curly braces and join them with ', '
    mat_str = ', '.join(['{' + inner + '}' for inner in inner_strings])

    return f'{{{mat_str}}}'

class OptimizationCommand:
    def __init__(self, action: Action):
        self.params_list = action.params
        self.action = action
        # A list of concerned computations of the actions
        self.comps = action.comps
        # We save the schedule of an action in each comp individually to form the whole schedule of a program later
        self.comps_schedule = {}
        self.tiramisu_optim_str = self.get_tiramisu_optim_str()

    def get_tiramisu_optim_str(self):
        """Convert the optimization command into Tiramisu code.
        Returns:
            str: The tiramisu snippet that represents the optimization command.
        """

        if isinstance(self.action, Interchange):
            assert len(self.params_list) == 2
            interchange_str = (
                ".interchange(" + ",".join([str(p) for p in self.params_list]) + ");"
            )
            optim_str = ""
            for comp in self.comps:
                self.comps_schedule[comp] = "I(L{},L{})".format(*self.params_list)
                optim_str += "\n\t{}".format(comp) + interchange_str
            return optim_str
        elif isinstance(self.action, Skewing):
            assert len(self.params_list) == 4
            skewing_str = ".skew(" + ",".join([str(p) for p in self.params_list]) + ");"
            optim_str = ""
            for comp in self.comps:
                self.comps_schedule[comp] = "S(L{},L{},{},{})".format(*self.params_list)
                optim_str += "\n\t{}".format(comp) + skewing_str
            return optim_str

        elif isinstance(self.action, Parallelization):
            assert len(self.params_list) == 1
            for comp in self.comps:
                self.comps_schedule[comp] = "P(L{})".format(self.params_list[0])
            return (
                "\n\t"
                + self.comps[0]
                + ".tag_parallel_level("
                + str(self.params_list[0])
                + ");"
            )

        elif isinstance(self.action, Tiling):
            assert len(self.params_list) == 4 or len(self.params_list) == 6
            tiling_str = ".tile(" + ",".join([str(p) for p in self.params_list]) + ");"
            optim_str = ""
            for comp in self.comps:
                if len(self.params_list) == 4:
                    self.comps_schedule[comp] = "T2(L{},L{},{},{})".format(
                        *self.params_list
                    )
                else:
                    self.comps_schedule[comp] = "T3(L{},L{},L{},{},{},{})".format(
                        *self.params_list
                    )
                optim_str += "\n\t{}".format(comp) + tiling_str
            return optim_str
        elif isinstance(self.action, Unrolling):
            optim_str = ""
            for comp in self.comps:
                self.comps_schedule[comp] = "U(L{},{})".format(*self.params_list)
                optim_str = (
                    f"\n\t{comp}.unroll({self.params_list[0]},{self.params_list[1]});"
                )
            # unrolling_str = (
            #     ".tag_unroll_level(" +
            #     ",".join([str(p) for p in self.params_list]) + ");")
            # optim_str += "\n\t{}".format(self.comps[0]) + unrolling_str
            return optim_str
        elif isinstance(self.action, Reversal):
            reversal_str = ".loop_reversal(" + str(self.params_list[0]) + ");"
            optim_str = ""
            for comp in self.comps:
                self.comps_schedule[comp] = "R(L{})".format(self.params_list[0])
                optim_str += "\n\t{}".format(comp) + reversal_str
            return optim_str
        elif isinstance(self.action, Fusion):
            self.fusion_str = f"F({self.params_list[0]},{self.params_list[1]})"
            return ""
        elif isinstance(self.action, AddingOne):
            matrix = np.copy(self.params_list[2])
            row, col = self.params_list[0], self.params_list[1]
            matrix[row][col] = matrix[row][col] +1
            addOne_str = ".matrix_transform("+ numpy_array_to_string(matrix) +");"
            optim_str = ""
            for comp in self.comps:
                self.comps_schedule[comp] = "A({},{})".format(self.params_list[0],self.params_list[1])
                optim_str += "\n\t{}".format(comp) + addOne_str
            return optim_str
        elif isinstance(self.action, OtherAction):
            return ""

    def __str__(self) -> str:
        return f"OptimizationCommand(action={self.action.__class__.__name__}, params={self.params_list})"

    def __repr__(self) -> str:
        return self.__str__()
