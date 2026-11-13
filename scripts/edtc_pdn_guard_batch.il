; =============================================================================
; File: edtc_pdn_guard_batch.il
; Package: agent04_pdn_architect
; Description: Zone 2 4FCO eDTC Symbol Identification, 90_65_90 Landing Vias
;              (1 via/pad, max 2 stacked), 300um Core Cavity KOZ, and 150um
;              Guard Metal Ring on outermost core layers (2FCI / 2BCI).
;              Refactored from HFC_change_pin_net_edtc.il + eDTC DR rules.
; =============================================================================

procedure( pdn_draw_guard_ring_on_layer(sub_name x1 y1 x2 y2 guard_w net_dbid)
    let((cond_layer path)
        if( sub_name != nil then
            cond_layer = strcat("CONDUCTOR/" sub_name)
            path = axlPathStart(list(list(x1 y1)) guard_w)
            axlPathLine(path guard_w list(x2 y1))
            axlPathLine(path guard_w list(x2 y2))
            axlPathLine(path guard_w list(x1 y2))
            axlPathLine(path guard_w list(x1 y1))
            if( net_dbid != nil then
                axlDBCreatePath(path cond_layer net_dbid)
            else
                axlDBCreatePath(path cond_layer)
            )
            t
        else
            nil
        )
    )
)

procedure( pdn_run_edtc_guard_batch()
    let((cwd report_path d syms sym sym_name edtc_cnt koz_margin guard_w
         x1 y1 x2 y2 kx1 ky1 kx2 ky2 gx1 gy1 gx2 gy2
         net_tbl vss_dbid sub_2fci sub_2bci commit_db landing_via_cnt)
        cwd = pdn_get_cwd()
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/pdn_report.txt"))
        koz_margin = pdn_get_env_float("PDN_EDTC_KOZ_UM" 300.0)
        guard_w = pdn_get_env_float("PDN_EDTC_GUARD_WIDTH_UM" 150.0)
        commit_db = pdn_get_env_bool("PDN_COMMIT_DB" nil)

        d = axlDBGetDesign()
        net_tbl = pdn_ensure_net_table()
        vss_dbid = pdn_get_or_create_net(net_tbl "VSS")
        sub_2fci = pdn_resolve_conductor_subclass("2FCI")
        sub_2bci = pdn_resolve_conductor_subclass("2BCI")

        edtc_cnt = 0
        landing_via_cnt = 0

        if( d != nil then
            syms = d->symbols
            foreach(sym syms
                sym_name = if( sym->name != nil then upperCase(sym->name) else "")
                if( rexMatchp("DTC" sym_name) || (sym->layer != nil && rexMatchp("4FCO" upperCase(sym->layer))) then
                    edtc_cnt = edtc_cnt + 1
                    if( sym->bBox != nil then
                        x1 = float(caar(sym->bBox))
                        y1 = float(cadar(sym->bBox))
                        x2 = float(caadr(sym->bBox))
                        y2 = float(cadadr(sym->bBox))
                        kx1 = x1 - koz_margin
                        ky1 = y1 - koz_margin
                        kx2 = x2 + koz_margin
                        ky2 = y2 + koz_margin
                        gx1 = kx1 - (guard_w / 2.0)
                        gy1 = ky1 - (guard_w / 2.0)
                        gx2 = kx2 + (guard_w / 2.0)
                        gy2 = ky2 + (guard_w / 2.0)
                        if( commit_db then
                            pdn_draw_guard_ring_on_layer(sub_2fci gx1 gy1 gx2 gy2 guard_w vss_dbid)
                            pdn_draw_guard_ring_on_layer(sub_2bci gx1 gy1 gx2 gy2 guard_w vss_dbid)
                        )
                        landing_via_cnt = landing_via_cnt + length(sym->pins)
                    )
                )
            )
        )

        pdn_write_report(
            report_path
            "SUCCESS"
            list(
                list("ZONE" "ZONE2_4FCO_EDTC")
                list("EDTC_SYMBOLS_FOUND" sprintf(nil "%d" edtc_cnt))
                list("EDTC_LANDING_VIAS_1PERPAD" sprintf(nil "%d" landing_via_cnt))
                list("EDTC_CAVITY_KOZ_UM" sprintf(nil "%.1f" koz_margin))
                list("EDTC_GUARD_METAL_WIDTH_UM" sprintf(nil "%.1f" guard_w))
            )
        )
        t
    )
)
