// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_sysController.h for the primary calling header

#include "Vtb_sysController__pch.h"
#include "Vtb_sysController__Syms.h"
#include "Vtb_sysController___024root.h"

void Vtb_sysController___024root___ctor_var_reset(Vtb_sysController___024root* vlSelf);

Vtb_sysController___024root::Vtb_sysController___024root(Vtb_sysController__Syms* symsp, const char* v__name)
    : VerilatedModule{v__name}
    , __VdlySched{*symsp->_vm_contextp__}
    , vlSymsp{symsp}
 {
    // Reset structure values
    Vtb_sysController___024root___ctor_var_reset(this);
}

void Vtb_sysController___024root::__Vconfigure(bool first) {
    if (false && first) {}  // Prevent unused
}

Vtb_sysController___024root::~Vtb_sysController___024root() {
}
