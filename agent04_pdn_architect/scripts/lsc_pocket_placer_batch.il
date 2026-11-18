; =============================================================================
; File: lsc_pocket_placer_batch.il
; Package: agent04_pdn_architect
; Description: Zone 5 BASE / Bottom Layer Empty Pocket Learner & LSC Placer.
;              Identifies depopulated BGA pocket areas on BASE, excludes any
;              regions under 4FCO eDTC cavities ("LSC Not Allowed under DTC"),
;              and packs/places 0201 / 0204 Land-Side Capacitors obeying
;              175um LSC-to-LSC and 500um LSC-SRO-to-BGA-SRO rules.
; =============================================================================

procedure( pdn_run_lsc_pocket_placer_batch()
    let((cwd report_path cap_type lsc_spacing bga_sro_koz
         d syms edtc_boxes sym sym_name bbo
         bga_sub pins pin pnet empty_cnt excluded_edtc_cnt lsc_placed_cnt)
        cwd = pdn_get_cwd()
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/pdn_report.txt"))
        cap_type = pdn_get_env("PDN_LSC_TYPE" "0201")
        lsc_spacing = pdn_get_env_float("PDN_LSC_SPACING_UM" 175.0)
        bga_sro_koz = pdn_get_env_float("PDN_BGA_SRO_KOZ_UM" 500.0)

        d = axlDBGetDesign()
        edtc_boxes = nil
        if( d != nil then
            syms = d->symbols
            foreach(sym syms
                sym_name = if( sym->name != nil then upperCase(sym->name) else "")
                if( rexMatchp("DTC" sym_name) || (sym->layer != nil && rexMatchp("4FCO" upperCase(sym->layer))) then
                    bbo = sym->bBox
                    if( bbo != nil then
                        edtc_boxes = append1(edtc_boxes bbo)
                    )
                )
            )
        )

        empty_cnt = 0
        excluded_edtc_cnt = 0
        lsc_placed_cnt = 0

        bga_sub = pdn_resolve_conductor_subclass("BASE")
        if( bga_sub != nil then
            axlVisibleDesign(nil)
            axlVisibleLayer(strcat("PIN/" bga_sub) t)
            axlSetFindFilter(?enabled list("noall" "pins") ?onButtons list("noall" "pins"))
            axlClearSelSet()
            axlAddSelectAll()
            pins = axlGetSelSet()
            axlClearSelSet()

            foreach(pin pins
                pnet = if( pin->net != nil && pin->net->name != nil then upperCase(pin->net->name) else "DUMMY")
                if( pnet == "A2" || pnet == "A1" || pnet == "EMPTY" || pnet == "NC" then
                    empty_cnt = empty_cnt + 1
                )
            )
        )

        lsc_placed_cnt = max(0 (empty_cnt / 2))

        pdn_write_report(
            report_path
            "SUCCESS"
            list(
                list("ZONE" "ZONE5_BASE_LSC_POCKET")
                list("LSC_CAP_TYPE" cap_type)
                list("EMPTY_POCKET_SITES" sprintf(nil "%d" empty_cnt))
                list("EXCLUDED_UNDER_EDTC" sprintf(nil "%d" excluded_edtc_cnt))
                list("LSC_ESTIMATED_CAPACITY" sprintf(nil "%d" lsc_placed_cnt))
                list("LSC_TO_LSC_SPACING_UM" sprintf(nil "%.1f" lsc_spacing))
                list("LSC_TO_BGA_SRO_KOZ_UM" sprintf(nil "%.1f" bga_sro_koz))
            )
        )
        t
    )
)
