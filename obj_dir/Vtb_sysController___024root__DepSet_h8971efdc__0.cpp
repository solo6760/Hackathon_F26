// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_sysController.h for the primary calling header

#include "Vtb_sysController__pch.h"
#include "Vtb_sysController__Syms.h"
#include "Vtb_sysController___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_sysController___024root___dump_triggers__act(Vtb_sysController___024root* vlSelf);
#endif  // VL_DEBUG

void Vtb_sysController___024root___eval_triggers__act(Vtb_sysController___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_sysController__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_sysController___024root___eval_triggers__act\n"); );
    // Body
    vlSelf->__VactTriggered.set(0U, ((IData)(vlSelf->tb_sysController__DOT__dut__DOT__rollVal) 
                                     != (IData)(vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__dut__DOT__rollVal__1)));
    vlSelf->__VactTriggered.set(1U, (((IData)(vlSelf->tb_sysController__DOT__clk) 
                                      & (~ (IData)(vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__clk__0))) 
                                     | ((~ (IData)(vlSelf->tb_sysController__DOT__n_rst)) 
                                        & (IData)(vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__n_rst__0))));
    vlSelf->__VactTriggered.set(2U, ((IData)(vlSelf->tb_sysController__DOT__clk) 
                                     & (~ (IData)(vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__clk__0))));
    vlSelf->__VactTriggered.set(3U, vlSelf->__VdlySched.awaitingCurrentTime());
    vlSelf->__VactTriggered.set(4U, ((~ (IData)(vlSelf->tb_sysController__DOT__clk)) 
                                     & (IData)(vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__clk__0)));
    vlSelf->__VactTriggered.set(5U, ((IData)(vlSelf->tb_sysController__DOT__ready) 
                                     != (IData)(vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__ready__0)));
    vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__dut__DOT__rollVal__1 
        = vlSelf->tb_sysController__DOT__dut__DOT__rollVal;
    vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__clk__0 
        = vlSelf->tb_sysController__DOT__clk;
    vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__n_rst__0 
        = vlSelf->tb_sysController__DOT__n_rst;
    vlSelf->__Vtrigprevexpr___TOP__tb_sysController__DOT__ready__0 
        = vlSelf->tb_sysController__DOT__ready;
    if (VL_UNLIKELY((1U & (~ (IData)(vlSelf->__VactDidInit))))) {
        vlSelf->__VactDidInit = 1U;
        vlSelf->__VactTriggered.set(0U, 1U);
        vlSelf->__VactTriggered.set(5U, 1U);
    }
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vtb_sysController___024root___dump_triggers__act(vlSelf);
    }
#endif
}
