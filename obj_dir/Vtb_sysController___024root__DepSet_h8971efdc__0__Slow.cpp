// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_sysController.h for the primary calling header

#include "Vtb_sysController__pch.h"
#include "Vtb_sysController__Syms.h"
#include "Vtb_sysController___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_sysController___024root___dump_triggers__stl(Vtb_sysController___024root* vlSelf);
#endif  // VL_DEBUG

VL_ATTR_COLD void Vtb_sysController___024root___eval_triggers__stl(Vtb_sysController___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_sysController__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_sysController___024root___eval_triggers__stl\n"); );
    // Body
    vlSelf->__VstlTriggered.set(0U, (IData)(vlSelf->__VstlFirstIteration));
    vlSelf->__VstlTriggered.set(1U, ((IData)(vlSelf->tb_sysController__DOT__dut__DOT__rollVal) 
                                     != (IData)(vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__dut__DOT__rollVal__0)));
    vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__dut__DOT__rollVal__0 
        = vlSelf->tb_sysController__DOT__dut__DOT__rollVal;
    if (VL_UNLIKELY((1U & (~ (IData)(vlSelf->__VstlDidInit))))) {
        vlSelf->__VstlDidInit = 1U;
        vlSelf->__VstlTriggered.set(1U, 1U);
    }
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vtb_sysController___024root___dump_triggers__stl(vlSelf);
    }
#endif
}
