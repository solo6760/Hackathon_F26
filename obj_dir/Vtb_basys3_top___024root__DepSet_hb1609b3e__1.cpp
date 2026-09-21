// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_basys3_top.h for the primary calling header

#include "Vtb_basys3_top__pch.h"
#include "Vtb_basys3_top___024root.h"

extern const VlUnpacked<CData/*0:0*/, 256> Vtb_basys3_top__ConstPool__TABLE_h9037dfb8_0;
extern const VlUnpacked<CData/*0:0*/, 256> Vtb_basys3_top__ConstPool__TABLE_h29348ae9_0;
extern const VlUnpacked<CData/*0:0*/, 256> Vtb_basys3_top__ConstPool__TABLE_h290102ed_0;
extern const VlUnpacked<CData/*0:0*/, 256> Vtb_basys3_top__ConstPool__TABLE_h95586c63_0;
extern const VlUnpacked<CData/*0:0*/, 256> Vtb_basys3_top__ConstPool__TABLE_hcc3ae6bf_0;
extern const VlUnpacked<CData/*0:0*/, 256> Vtb_basys3_top__ConstPool__TABLE_h81f217b0_0;
extern const VlUnpacked<CData/*3:0*/, 256> Vtb_basys3_top__ConstPool__TABLE_h0a976bea_0;
extern const VlUnpacked<CData/*1:0*/, 256> Vtb_basys3_top__ConstPool__TABLE_h56ef9f15_0;

VL_INLINE_OPT void Vtb_basys3_top___024root___nba_comb__TOP__3(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___nba_comb__TOP__3\n"); );
    // Init
    CData/*7:0*/ __Vtableidx2;
    __Vtableidx2 = 0;
    // Body
    __Vtableidx2 = (((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__drain_start) 
                     << 7U) | (((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__tile_start) 
                                << 6U) | (((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__fifo_full) 
                                           << 5U) | 
                                          (((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__roll_flag) 
                                            << 4U) 
                                           | (((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__mem_wr_valid) 
                                               << 3U) 
                                              | (((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__fifo_empty) 
                                                  << 2U) 
                                                 | (IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__counter_state)))))));
    vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__fifo_wr_en 
        = Vtb_basys3_top__ConstPool__TABLE_h9037dfb8_0
        [__Vtableidx2];
    vlSelf->tb_basys3_top__DOT__dut__DOT__ready = Vtb_basys3_top__ConstPool__TABLE_h29348ae9_0
        [__Vtableidx2];
    vlSelf->tb_basys3_top__DOT__dut__DOT__drain_active 
        = Vtb_basys3_top__ConstPool__TABLE_h290102ed_0
        [__Vtableidx2];
    vlSelf->tb_basys3_top__DOT__dut__DOT__computer_active 
        = Vtb_basys3_top__ConstPool__TABLE_h95586c63_0
        [__Vtableidx2];
    vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__counter_clear 
        = Vtb_basys3_top__ConstPool__TABLE_hcc3ae6bf_0
        [__Vtableidx2];
    vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__counter_enable 
        = Vtb_basys3_top__ConstPool__TABLE_h81f217b0_0
        [__Vtableidx2];
    vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__rollVal 
        = Vtb_basys3_top__ConstPool__TABLE_h0a976bea_0
        [__Vtableidx2];
    vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__next_counter 
        = Vtb_basys3_top__ConstPool__TABLE_h56ef9f15_0
        [__Vtableidx2];
    vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__inst_count__DOT__next_val 
        = (((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__counter_clear) 
            | ((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__counter_state) 
               != (IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__next_counter)))
            ? 0U : (0xfU & ((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__counter_enable)
                             ? (((IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__inst_count__DOT__val) 
                                 >= (IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__rollVal))
                                 ? 0U : ((IData)(1U) 
                                         + (IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__inst_count__DOT__val)))
                             : (IData)(vlSelf->tb_basys3_top__DOT__dut__DOT__u_sys__DOT__inst_count__DOT__val))));
}

void Vtb_basys3_top___024root___nba_sequent__TOP__0(Vtb_basys3_top___024root* vlSelf);
void Vtb_basys3_top___024root___nba_sequent__TOP__1(Vtb_basys3_top___024root* vlSelf);
void Vtb_basys3_top___024root___act_comb__TOP__0(Vtb_basys3_top___024root* vlSelf);
void Vtb_basys3_top___024root___nba_sequent__TOP__2(Vtb_basys3_top___024root* vlSelf);
void Vtb_basys3_top___024root___nba_comb__TOP__1(Vtb_basys3_top___024root* vlSelf);
void Vtb_basys3_top___024root___nba_comb__TOP__2(Vtb_basys3_top___024root* vlSelf);
void Vtb_basys3_top___024root___act_comb__TOP__1(Vtb_basys3_top___024root* vlSelf);

void Vtb_basys3_top___024root___eval_nba(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___eval_nba\n"); );
    // Body
    if ((2ULL & vlSelf->__VnbaTriggered.word(0U))) {
        Vtb_basys3_top___024root___nba_sequent__TOP__0(vlSelf);
        vlSelf->__Vm_traceActivity[4U] = 1U;
    }
    if ((4ULL & vlSelf->__VnbaTriggered.word(0U))) {
        Vtb_basys3_top___024root___nba_sequent__TOP__1(vlSelf);
        vlSelf->__Vm_traceActivity[5U] = 1U;
    }
    if ((0x3aULL & vlSelf->__VnbaTriggered.word(0U))) {
        Vtb_basys3_top___024root___act_comb__TOP__0(vlSelf);
    }
    if ((2ULL & vlSelf->__VnbaTriggered.word(0U))) {
        Vtb_basys3_top___024root___nba_sequent__TOP__2(vlSelf);
        vlSelf->__Vm_traceActivity[6U] = 1U;
    }
    if ((5ULL & vlSelf->__VnbaTriggered.word(0U))) {
        Vtb_basys3_top___024root___nba_comb__TOP__1(vlSelf);
    }
    if ((6ULL & vlSelf->__VnbaTriggered.word(0U))) {
        Vtb_basys3_top___024root___nba_comb__TOP__2(vlSelf);
        vlSelf->__Vm_traceActivity[7U] = 1U;
    }
    if ((7ULL & vlSelf->__VnbaTriggered.word(0U))) {
        Vtb_basys3_top___024root___nba_comb__TOP__3(vlSelf);
        vlSelf->__Vm_traceActivity[8U] = 1U;
    }
    if ((0x3fULL & vlSelf->__VnbaTriggered.word(0U))) {
        Vtb_basys3_top___024root___act_comb__TOP__1(vlSelf);
    }
}

void Vtb_basys3_top___024root___timing_resume(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___timing_resume\n"); );
    // Body
    if ((0x10ULL & vlSelf->__VactTriggered.word(0U))) {
        vlSelf->__VtrigSched_h64922b81__0.resume("@(negedge tb_basys3_top.clk)");
    }
    if ((0x20ULL & vlSelf->__VactTriggered.word(0U))) {
        vlSelf->__VtrigSched_hf9883bcd__0.resume("@([changed] tb_basys3_top.led[1])");
    }
    if ((8ULL & vlSelf->__VactTriggered.word(0U))) {
        vlSelf->__VdlySched.resume();
    }
}

void Vtb_basys3_top___024root___timing_commit(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___timing_commit\n"); );
    // Body
    if ((! (0x10ULL & vlSelf->__VactTriggered.word(0U)))) {
        vlSelf->__VtrigSched_h64922b81__0.commit("@(negedge tb_basys3_top.clk)");
    }
    if ((! (0x20ULL & vlSelf->__VactTriggered.word(0U)))) {
        vlSelf->__VtrigSched_hf9883bcd__0.commit("@([changed] tb_basys3_top.led[1])");
    }
}

void Vtb_basys3_top___024root___eval_triggers__act(Vtb_basys3_top___024root* vlSelf);
void Vtb_basys3_top___024root___eval_act(Vtb_basys3_top___024root* vlSelf);

bool Vtb_basys3_top___024root___eval_phase__act(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___eval_phase__act\n"); );
    // Init
    VlTriggerVec<6> __VpreTriggered;
    CData/*0:0*/ __VactExecute;
    // Body
    Vtb_basys3_top___024root___eval_triggers__act(vlSelf);
    Vtb_basys3_top___024root___timing_commit(vlSelf);
    __VactExecute = vlSelf->__VactTriggered.any();
    if (__VactExecute) {
        __VpreTriggered.andNot(vlSelf->__VactTriggered, vlSelf->__VnbaTriggered);
        vlSelf->__VnbaTriggered.thisOr(vlSelf->__VactTriggered);
        Vtb_basys3_top___024root___timing_resume(vlSelf);
        Vtb_basys3_top___024root___eval_act(vlSelf);
    }
    return (__VactExecute);
}

bool Vtb_basys3_top___024root___eval_phase__nba(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___eval_phase__nba\n"); );
    // Init
    CData/*0:0*/ __VnbaExecute;
    // Body
    __VnbaExecute = vlSelf->__VnbaTriggered.any();
    if (__VnbaExecute) {
        Vtb_basys3_top___024root___eval_nba(vlSelf);
        vlSelf->__VnbaTriggered.clear();
    }
    return (__VnbaExecute);
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_basys3_top___024root___dump_triggers__nba(Vtb_basys3_top___024root* vlSelf);
#endif  // VL_DEBUG
#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_basys3_top___024root___dump_triggers__act(Vtb_basys3_top___024root* vlSelf);
#endif  // VL_DEBUG

void Vtb_basys3_top___024root___eval(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___eval\n"); );
    // Init
    IData/*31:0*/ __VnbaIterCount;
    CData/*0:0*/ __VnbaContinue;
    // Body
    __VnbaIterCount = 0U;
    __VnbaContinue = 1U;
    while (__VnbaContinue) {
        if (VL_UNLIKELY((0x64U < __VnbaIterCount))) {
#ifdef VL_DEBUG
            Vtb_basys3_top___024root___dump_triggers__nba(vlSelf);
#endif
            VL_FATAL_MT("Kade_RTL/tb/tb_basys3_top.sv", 3, "", "NBA region did not converge.");
        }
        __VnbaIterCount = ((IData)(1U) + __VnbaIterCount);
        __VnbaContinue = 0U;
        vlSelf->__VactIterCount = 0U;
        vlSelf->__VactContinue = 1U;
        while (vlSelf->__VactContinue) {
            if (VL_UNLIKELY((0x64U < vlSelf->__VactIterCount))) {
#ifdef VL_DEBUG
                Vtb_basys3_top___024root___dump_triggers__act(vlSelf);
#endif
                VL_FATAL_MT("Kade_RTL/tb/tb_basys3_top.sv", 3, "", "Active region did not converge.");
            }
            vlSelf->__VactIterCount = ((IData)(1U) 
                                       + vlSelf->__VactIterCount);
            vlSelf->__VactContinue = 0U;
            if (Vtb_basys3_top___024root___eval_phase__act(vlSelf)) {
                vlSelf->__VactContinue = 1U;
            }
        }
        if (Vtb_basys3_top___024root___eval_phase__nba(vlSelf)) {
            __VnbaContinue = 1U;
        }
    }
}

#ifdef VL_DEBUG
void Vtb_basys3_top___024root___eval_debug_assertions(Vtb_basys3_top___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_basys3_top__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_basys3_top___024root___eval_debug_assertions\n"); );
}
#endif  // VL_DEBUG
