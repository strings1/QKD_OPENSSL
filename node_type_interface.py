#== Author: Darie Alexandru ===========================================#
# This file defines the abstract base class for QKD node types.       #
#======================================================================#

from abc import ABC, abstractmethod
import os

class QKD_Node(ABC):
    basis = ['+', 'X']
    colors = {
        basis[0]: {
            '0': 'Blue',
            '1': 'Green'
        },
        basis[1]: {
            '0': 'Blue',
            '1': 'Red'
        }
    }

    @abstractmethod
    def read(self):
        pass

    @abstractmethod
    def write(self, data):
        pass

    @abstractmethod
    def calibrate(self):
        pass