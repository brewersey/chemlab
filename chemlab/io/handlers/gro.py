import numpy as np
import re

from .base import IOHandler
from .gro_map import gro_to_cl

from ...core.system import System
from ...core.molecule import Atom
from ...data.symbols import symbol_list


symbol_list = [s.lower() for s in symbol_list]

class GromacsIO(IOHandler):
    '''Handler for .gro file format. Example at
    http://manual.gromacs.org/online/gro.html.
    
    **Features**

    .. method:: read("system")
    
       Read the gro file and return a :py:class:`~chemlab.core.System`
       instance. It also add the following exporting informations:
    
       groname: The molecule names indicated in the gro file. This is
            added to each entry of `System.mol_export`.

       grotype: The atom names as indicated in the gro file. This is
            added to each entry of `System.atom_export_array`.
       
    .. method:: write("system", syst)
    
       Write the *syst* :py:class:`~chemlab.core.System` instance to
       disk. The export arrays should have the *groname* and *grotype*
       entries as specified in the ``read("system")`` method.

    **Example**
    
    Export informations for water SPC::
    
         Molecule([
                   Atom('O', [0.0, 0.0, 0.0], export={'grotype': 'OW'}),
                   Atom('H', [0.1, 0.0, 0.0], export={'grotype': 'HW1'}),
                   Atom('H', [-0.033, 0.094, 0.0],export={'grotype':'HW2'})],
                 export={'groname': 'SOL'})

    '''
    
    can_read = ['system']
    can_write = ['system']

    def __init__(self, filename):
        self.filename = filename
    
    def read(self, feature):
        if feature == 'system':
            with open(self.filename) as fn:
                lines = fn.readlines()
                return parse_gro_lines(lines)


    def write(self, feature, sys):
        if feature == 'system':
            write_gro(sys, self.filename)


def parse_gro_lines(lines):
    '''Reusable parsing'''
    title = lines.pop(0)
    natoms = int(lines.pop(0))
    atomlist = []
    
    # I need r_array, type_array, 
    datalist = []
    for l in lines:
        fields = l.split()
        line_length = len(l)
        
        if line_length == 45 or line_length == 69:
            #Only positions are provided
            molidx = int(l[0:5])
            moltyp = l[5:10].strip()
            attyp = l[10:15].strip()
            atidx  = int(l[15:20])
            rx     = float(l[20:28])
            ry     = float(l[28:36])
            rz     = float(l[36:44])
            
            hasvel = False
            if line_length == 69:
                hasvel = True
                # Provide velocities
                vx     = float(l[44:52])
                vy     = float(l[52:60])
                vz     = float(l[60:68])
            
            # Do I have to convert back the atom types, probably yes???
            #if attyp.lower() not in symbol_list:
            #    attyp = gro_to_cl[attyp]
            datalist.append((molidx, moltyp, attyp, rx, ry, rz))
        else:
            # This is the box size
            a, b, c = [float(f) for f in fields]
            box_vectors = np.array([[a,0,0], [0,b,0], [0,0,c]])
            break
    
    dataarr = np.array(datalist, dtype=np.dtype([('f0', int), ('f1', object),
                                                 ('f2', object), ('f3', np.float64),
                                                 ('f4', np.float64), ('f5', np.float64)]))

    # Molecule indices: unique elements in molidx
    mol_id, mol_indices = np.unique(dataarr['f0'], return_index=True)
    r_array = np.vstack([dataarr['f3'], dataarr['f4'], dataarr['f5']]).transpose()
    grotype_array = dataarr['f2']
        
    mol_export = np.array([dict(groname=g) for g in dataarr['f1'][mol_indices]])
    atom_export_array = np.array([dict(grotype=g) for g in grotype_array])
    
    # Gromacs Defaults to Unknown Atom type
    type_array = np.array([gro_to_cl.get(g, "Unknown") for g in grotype_array])
    
    # Molecular Formula Arrays
    mol_formula = []
    end = len(r_array)
    for i, _ in enumerate(mol_indices):
        s = mol_indices[i]
        e = mol_indices[i+1] if i+1 < len(mol_indices) else end
        from chemlab.core.molecule import make_formula
        mol_formula.append(make_formula(type_array[s:e]))
        
    mol_formula = np.array(mol_formula)
    
    
    # n_mol, n_at
    sys = System.from_arrays(r_array=r_array, mol_indices=mol_indices,
                                 type_array=type_array,
                                 atom_export_array=atom_export_array,
                                 mol_export=mol_export,
                                 mol_formula=mol_formula,
                                 box_vectors=box_vectors)
    
    #sys.r_array -= boxsize/2.0
    
    return sys
                
def write_gro(sys, filename):
    lines = []
    lines.append('Generated by chemlab')
    lines.append('{:>5}'.format(sys.n_atoms))
    
    at_n = 0
    # Residue Number
    for i in xrange(sys.n_mol):
        res_n = i + 1
        
        try:
            res_name = sys.mol_export[i]['groname']
        except KeyError:
            raise Exception('Gromacs exporter need the residue name as groname')

        for j in xrange(sys.mol_n_atoms[i]):
            offset = sys.mol_indices[i]
            
            try:
                at_name = sys.atom_export_array[offset+j]['grotype']
            except KeyError:
                raise Exception('Gromacs exporter needs the atom type as grotype')
            
            at_n += 1
            x, y, z = sys.r_array[offset+j]# + sys.boxsize / 2.0
            
            lines.append('{:>5}{:<5}{:>5}{:>5}{:>8.3f}{:>8.3f}{:>8.3f}'
                         .format(res_n, res_name, at_name, at_n%99999, x, y, z))
    
    if sys.box_vectors == None:
        raise Exception('Gromacs exporter need box_vector information\nSet System.boxsize attribute or System.box_vectors')
    lines.append('{:>10.5f}{:>10.5f}{:>10.5f}'.format(sys.box_vectors[0,0],
                                                      sys.box_vectors[1,1],
                                                      sys.box_vectors[2,2]))
    
    #for line in lines:
    #    print line
        
    lines = [l + '\n' for l in lines]
    
    with open(filename, 'w') as fn:
        fn.writelines(lines)
        
