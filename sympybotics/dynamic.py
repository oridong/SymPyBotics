# -*- coding: utf-8 -*-

###############################################################################
#  SymPyBotics: Symbolic Robotics Toolbox using Python and SymPy
#
#      Copyright (C) 2012 Cristóvão Sousa <crisjss@gmail.com>
#
#  Distributed under the terms of the GNU General Public License (GPL),
#  version 2 or any later version.  The full text of the GPL is available at:
#                  http://www.gnu.org/licenses/
###############################################################################


import copy
import sympy
import numpy

from . import intermediate


def skew(v):
  return sympy.Matrix( [ [     0, -v[2],  v[1] ],
                   [  v[2],     0, -v[0] ],
                   [ -v[1],  v[0],     0 ] ] )


def Adj(G,g):
  R = G[0:3,0:3];  p = G[0:3,3]
  return ( R.row_join(sympy.zeros(3)) ).col_join( (skew(p)*R).row_join(R) ) * g

def Adjdual(G,g):
  R = G[0:3,0:3];  p = G[0:3,3]
  return ( ( R.row_join(sympy.zeros(3)) ).col_join( (skew(p)*R).row_join(R) ) ).transpose() * g

def adj(g,h):
  wg = g[0:3,0];  vg = g[3:6,0]
  return ( skew(wg).row_join(sympy.zeros(3)) ).col_join( (skew(vg)).row_join(skew(wg)) ) * h

def adjdual(g,h):
  wg = g[0:3,0];  vg = g[3:6,0]
  return ( ( skew(wg).row_join(sympy.zeros(3)) ).col_join( (skew(vg)).row_join(skew(wg)) ) ).transpose() * h


def gen_fricterm( rbt ):
  fric = sympy.zeros((rbt.dof,1))
  for i in range( rbt.dof ):
    fric[i] = rbt.fv[i] * rbt.dq[i] + rbt.fc[i] * sympy.sign(rbt.dq[i])
  return fric


def _forward_rne( rbt, m_intervar_func=None ):
  
  Vi = list(range(0,rbt.dof+1))
  dVi = list(range(0,rbt.dof+1))

  Vi[0] = sympy.zeros((6,1))
  dVi[0] = - sympy.zeros((3,1)).col_join( rbt.gravity )

  # Forward
  for i in range(1,rbt.dof+1):

    Vi[i] =  Adj( rbt.Tdhi_inv[i], Vi[i-1] )  +  rbt.Si[i] * rbt.dq[i-1]
    if m_intervar_func: Vi[i] = m_intervar_func( Vi[i] , 'V_'+str(i) )

    dVi[i] =  rbt.Si[i] * rbt.ddq[i-1]  +  Adj( rbt.Tdhi_inv[i], dVi[i-1] )  +  adj(  Adj( rbt.Tdhi_inv[i], Vi[i-1] ),  rbt.Si[i] * rbt.dq[i-1] )

    if m_intervar_func: dVi[i] = m_intervar_func( dVi[i] , 'dV_'+str(i) )

  return Vi, dVi


def _backward_rne( rbt, LLi, Vi, dVi, m_intervar_func=None ):

  Tdhi_inv = copy.copy( rbt.Tdhi_inv )
  Tdhi_inv.append( sympy.eye(4) )

  Fi = list(range(0,rbt.dof+2))
  tau = sympy.zeros((rbt.dof,1))

  Fi[rbt.dof+1] = copy.copy( sympy.zeros((6,1)) )

  # Backward
  for i in range(rbt.dof,0,-1):

    Fi[i] =  Adjdual( Tdhi_inv[i+1], Fi[i+1] )  +  LLi[i] * dVi[i]  -  adjdual( Vi[i],  LLi[i] * Vi[i] )

    if m_intervar_func: Fi[i] = m_intervar_func( Fi[i] , 'F_'+str(i) )

    tau[i-1] =  ( rbt.Si[i].transpose() *  Fi[i] )[0]

  return tau






def gen_tau_rne( gen_intervars, rbt ):
      
  LLi = list(range(0,rbt.dof+1))

  for i in range( rbt.dof ):
    LLi[i+1] = ( rbt.L[i].row_join(skew(rbt.r[i])) ).col_join( (-skew( rbt.r[i]) ).row_join(sympy.eye(3)*rbt.m[i]) )

  ivars = []
  m_intervar_func = intermediate.genfunc_m_intervar( gen_intervars, ivars )

  Vi, dVi = _forward_rne( rbt, m_intervar_func )
  tau = _backward_rne( rbt, LLi, Vi, dVi, m_intervar_func )

  if gen_intervars:
      return ivars,tau
  else:
      return tau



def gen_regressor_rne( gen_intervars, rbt, usefricdyn = True ):

  if usefricdyn:
    fric = gen_fricterm(rbt)

  ivars = []
  m_intervar_func = intermediate.genfunc_m_intervar( gen_intervars, ivars )

  Vi, dVi = _forward_rne( rbt, m_intervar_func )

  dynparms = rbt.dynparms( usefricdyn = usefricdyn )

  Y = sympy.zeros( ( rbt.dof, len(dynparms) ) )

  cancel_dict = dict( zip( dynparms, [0]*len(dynparms) ) )

  for p,parm in enumerate(dynparms):

    select = copy.copy(cancel_dict)
    select.update( { parm: 1 } )

    LLi = list(range(0,rbt.dof+1))

    for i in range( rbt.dof ):
      LLi[i+1] = ( ( rbt.L[i].row_join(skew(rbt.r[i])) ).col_join( (-skew( rbt.r[i]) ).row_join(sympy.eye(3)*rbt.m[i]) ) ).subs(select)

    Y[:,p] = _backward_rne( rbt, LLi, Vi, dVi, m_intervar_func )

    if usefricdyn:
      Y[:,p] += fric.subs(select)

  if gen_intervars:
      return ivars , Y
  else:
      return Y



def gen_gravterm_rne( gen_intervars, rbt ):
  rbttmp = copy.deepcopy(rbt)
  rbttmp.dq = sympy.zeros((rbttmp.dof,1))
  rbttmp.ddq = sympy.zeros((rbttmp.dof,1))
  rbttmp.gen_geometric_model()
  return gen_tau_rne( gen_intervars, rbttmp )


def gen_ccfterm_rne( gen_intervars, rbt ):
  rbttmp = copy.deepcopy(rbt)
  rbttmp.gravity = sympy.zeros((3,1))
  rbttmp.ddq = sympy.zeros((rbttmp.dof,1))
  rbttmp.gen_geometric_model()
  return gen_tau_rne( gen_intervars, rbttmp )



def gen_massmatrix_rne( gen_intervars, rbt ):

  LLi = list(range(0,rbt.dof+1))

  for i in range( rbt.dof ):
    LLi[i+1] = ( rbt.L[i].row_join(skew(rbt.r[i])) ).col_join( (-skew( rbt.r[i]) ).row_join(sympy.eye(3)*rbt.m[i]) )

  ivars = []
  m_intervar_func = intermediate.genfunc_m_intervar( gen_intervars, ivars )

  M = sympy.zeros((rbt.dof,rbt.dof))

  rbttmp = copy.deepcopy( rbt )
  rbttmp.gravity = sympy.zeros((3,1))
  rbttmp.dq = sympy.zeros((rbttmp.dof,1))

  for i in range( M.rows ):
    rbttmp.ddq = sympy.zeros((rbttmp.dof,1))
    rbttmp.ddq[i] = 1
    rbttmp.gen_geometric_model()

    Vi, dVi = _forward_rne( rbttmp, m_intervar_func )
    Mcoli = _backward_rne( rbttmp, LLi, Vi, dVi, m_intervar_func = m_intervar_func )

    # It's done like this since M is symmetric:
    M[:,i] = ( M[i,:i].T ) .col_join( Mcoli[i:,:] )

  if gen_intervars:
    return ivars , M
  else:
    return M










def linear_dependencies( m , err_dec = 20, round_dec = 10 ):

    W = m
    
    (nr,nc) = W.shape

    d = numpy.identity(nc)

    if not W[:,0].any():
        d[0,0] = 0.0

    for i in range(1,nc):
        if not W[:,i].any():
            d[i,i] = 0.0
        else:
            A = W[:,:i]
            b = W[:,i:i+1]
            Api = numpy.linalg.pinv(A)
            x = numpy.dot(Api,b)
            err = numpy.linalg.norm(b - numpy.dot(A,x))
            if err < 10.0**(-err_dec):
                d[:,i:i+1] = numpy.vstack(( x.reshape(i,1),numpy.zeros((nc-i,1)) ))
                W[:,i:i+1] = numpy.zeros((nr,1))

    return d.round(round_dec)



def find_parm_dependencies_numeric( dof, Pn, Y_func, Y_rows=None, samples=1000, err_dec = 5, round_dec = 6 ):

  pi = numpy.pi

  if not Y_rows: Y_rows = dof

  W = numpy.zeros( ( Y_rows*samples, Pn ) )
  for i in range(samples):
    q = [ float( numpy.random.random()*2.0*pi - pi ) for j in range(dof) ]
    dq = [ float( numpy.random.random()*2.0*pi - pi ) for j in range(dof) ]
    ddq = [ float( numpy.random.random()*2.0*pi - pi ) for j in range(dof) ]
    W[ i*Y_rows : i*Y_rows+Y_rows , : ] = numpy.matrix( Y_func( q, dq, ddq ) ).reshape( Y_rows, Pn )

  deps = linear_dependencies( W, err_dec, round_dec )

  return deps

