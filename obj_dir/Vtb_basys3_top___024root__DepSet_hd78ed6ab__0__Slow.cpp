// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_basys3_top.h for the primary calling header

#include "Vtb_basys3_top__pch.h"
#include "Vtb_basys3_top__Syms.h"
#include "Vtb_basys3_top___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_basys3_top___024root___dump_triggers__stl(Vtb_basys3_top___024root* vlSelf);
#endif  // VL_DEBUG

VL_ATTR_COLD void Vtb_basys3_top___024root___eval_triggers__stl(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___eval_triggers__stl\n"); );
    // Body
    vlSelf->__VstlTriggered.set(0U, (IData)(vlSelf->__VstlFirstIteration));
    vlSelf->__VstlTriggered.set(1U, ((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__rollVal) 
                                     != (IData)(vlSelf->__Vtrigprevexpr___TOP__tb_basys3_top__DOT__dut__DOT__u_sys__DOT__rollVal__0)));
    vlSelf->__Vtrigprevexpr___TOP__tb_basys3_top__DOT__dut__DOT__u_sys__DOT__rollVal__0 
        = vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__rollVal;
    if (VL_UNLIKELY((1U & (~ (IData)(vlSelf->__VstlDidInit))))) {
        vlSelf->__VstlDidInit = 1U;
        vlSelf->__VstlTriggered.set(1U, 1U);
    }
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vtb_basys3_top___024root___dump_triggers__stl(vlSelf);
    }
#endif
}
