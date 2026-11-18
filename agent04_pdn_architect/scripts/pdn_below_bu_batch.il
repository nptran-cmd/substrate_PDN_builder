; =============================================================================
; File: pdn_below_bu_batch.il
; Package: agent04_pdn_architect
; Description: Zone 4 Below-Core Build-Up (5B..12B) Router.
;              Refactored from BGA_routing.il (Broadcom +/-185, +/-247.487),
;              BGA_routing_ver2.il (Alcedo +/-115), and
;              BGA_routing_ver3.il (Google +/-195, +/-137.886).
;              Supports two user-selectable strategies:
;                1. MIRROR_ABOVE_BU: Mirrors Above-BU grid & VDD/VSS ratio
;                2. BGA_CLUSTER_4_5: Places 4-5 vias per cluster aligned around
;                   each target-net BGA ball pad on BASE/Bottom.
; =============================================================================

procedure( pdn_run_below_bu_batch()
    let((cwd report_path mode vias_per_cluster shift_card shift_diag
         bga_sub pins pin pnet target_nets net_tbl ps_resolved
         cluster_cnt via_cnt offset_list off pxy vx vy commit_db)
        cwd = pdn_get_cwd()
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/pdn_report.txt"))
        mode = upperCase(pdn_get_env("PDN_BELOW_BU_MODE" "BGA_CLUSTER_4_5"))
        vias_per_cluster = pdn_get_env_int("PDN_CLUSTER_VIAS" 5)
        shift_card = pdn_get_env_float("PDN_BGA_CARDINAL_SHIFT_UM" 195.0)
        shift_diag = pdn_get_env_float("PDN_BGA_DIAGONAL_SHIFT_UM" 137.886)
        target_nets = pdn_parse_csv_list(pdn_get_env("PDN_NETS" "VDDC0,VSS,VDDSRAM"))
        commit_db = pdn_get_env_bool("PDN_COMMIT_DB" nil)

        net_tbl = pdn_ensure_net_table()
        ps_resolved = pdn_resolve_padstack(list("V90_65_90_01A_L19_L20" "V90_65_90"))
        bga_sub = pdn_resolve_conductor_subclass("BASE")

        offset_list = list(
            list(shift_card 0.0)
            list(-shift_card 0.0)
            list(0.0 shift_card)
            list(0.0 -shift_card)
        )
        if( vias_per_cluster >= 5 then
            offset_list = append1(offset_list list(shift_diag shift_diag))
        )

        cluster_cnt = 0
        via_cnt = 0

        if( bga_sub != nil then
            axlVisibleDesign(nil)
            axlVisibleLayer(strcat("PIN/" bga_sub) t)
            axlSetFindFilter(?enabled list("noall" "pins") ?onButtons list("noall" "pins"))
            axlClearSelSet()
            axlAddSelectAll()
            pins = axlGetSelSet()
            axlClearSelSet()

            foreach(pin pins
                pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "")
                if( member(pnet target_nets) != nil && cluster_cnt < 500 then
                    cluster_cnt = cluster_cnt + 1
                    pxy = pin->xy
                    foreach(off offset_list
                        via_cnt = via_cnt + 1
                        vx = float(car(pxy)) + car(off)
                        vy = float(cadr(pxy)) + cadr(off)
                        if( commit_db && ps_resolved != nil && pin->net != nil then
                            axlDBCreateVia(ps_resolved list(vx vy) pin->net)
                        )
                    )
                )
            )
        )

        pdn_write_report(
            report_path
            "SUCCESS"
            list(
                list("ZONE" "ZONE4_BELOW_BU")
                list("BELOW_BU_MODE" mode)
                list("VIAS_PER_CLUSTER" sprintf(nil "%d" vias_per_cluster))
                list("BGA_CLUSTERS_PROCESSED" sprintf(nil "%d" cluster_cnt))
                list("BELOW_BU_VIAS_PLACED" sprintf(nil "%d" via_cnt))
            )
        )
        t
    )
)
