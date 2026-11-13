; =============================================================================
; File: base_lsc_bga_router_batch.il
; Package: agent04_pdn_architect
; Description: Complete Step 3 (BASE / BOTTOM Layer) Empty-BGA Pocket 0201 LSC
;              Max-Packer & 3-Option BGA/LSC Via-Cluster SKILL Router for
;              Cadence Allegro / APD (.mcm).
;
;              Implements ALL Step 3 Functions Natively in SKILL:
;                1. pdn_get_bga_via_offsets_skill(pattern_opt):
;                     Returns 12B->BASE (V90_65_90_12B_BASE_01A) via offsets for:
;                       - OPTION1_4VIA_SQUARE_2X2 (4 vias at ±110, ±110 um)
;                       - OPTION2_5VIA_QUINCUNX   (5 vias: center + ±135, ±135 um)
;                       - OPTION3_6VIA_HEX_RING   (6 vias: R=195 um hex ring)
;                2. pdn_get_lsc_pad_via_offsets_skill(rot_deg):
;                     Returns 3 via offsets on Pin 1 (VDDUC0) and 3 via offsets
;                     on Pin 2 (VSS) (6 vias per 0201 LSC on 348x348 um pads).
;                3. pdn_pack_1d_centers_skill(min_e max_e span pitch) &
;                   pdn_maximize_0201_lsc_in_pocket_skill(...):
;                     2D Mixed-Orientation (0 deg + 90 deg remainder strip)
;                     Max-Packing solver enforcing BGA-SRO-to-LSC-SRO >= 500um
;                     and LSC-SRO-to-LSC-SRO >= 175um / 250um.
;                4. pdn_route_base_lsc_and_bga_full_skill(bga_via_opt sro_um):
;                     Standalone end-to-end SKILL execution on the .mcm DB.
;                5. pdn_import_base_lsc_bga_recipe_batch():
;                     High-speed O(N) makeTable pipe-delimited recipe importer.
; =============================================================================

; -----------------------------------------------------------------------------
; 1. 3 Selectable BGA Via Cluster Pattern Options (12B -> BASE)
; -----------------------------------------------------------------------------
procedure( pdn_get_bga_via_offsets_skill(pattern_opt)
    let((u)
        u = upperCase(pattern_opt)
        if( rexMatchp("1" u) || rexMatchp("4VIA" u) || rexMatchp("SQUARE" u) || rexMatchp("2X2" u) then
            list(
                list(-110.0 -110.0)
                list( 110.0 -110.0)
                list(-110.0  110.0)
                list( 110.0  110.0)
            )
        else
            if( rexMatchp("2" u) || rexMatchp("5VIA" u) || rexMatchp("QUINCUNX" u) then
                list(
                    list(   0.0    0.0)
                    list(-135.0 -135.0)
                    list( 135.0 -135.0)
                    list(-135.0  135.0)
                    list( 135.0  135.0)
                )
            else
                ; OPTION3_6VIA_HEX_RING (R = 195.0 um)
                list(
                    list(   0.0  195.0)
                    list(   0.0 -195.0)
                    list(-137.9  137.9)
                    list( 137.9  137.9)
                    list(-137.9 -137.9)
                    list( 137.9 -137.9)
                )
            )
        )
    )
)

; -----------------------------------------------------------------------------
; 2. 0201 LSC Pad Via Offsets (3 Vias on Pin 1 + 3 Vias on Pin 2 = 6 Vias/LSC)
; -----------------------------------------------------------------------------
procedure( pdn_get_lsc_pad_via_offsets_skill(rot_deg)
    let((r_int p1_y p2_y p1_x p2_x p1_vias p2_vias)
        r_int = mod(round(float(rot_deg)) 360)
        cond(
            ( r_int == 0
                p1_y =  355.0
                p2_y = -355.0
                p1_vias = list(list(-93.0 p1_y) list(0.0 p1_y) list(93.0 p1_y))
                p2_vias = list(list(-93.0 p2_y) list(0.0 p2_y) list(93.0 p2_y))
            )
            ( r_int == 180
                p1_y = -355.0
                p2_y =  355.0
                p1_vias = list(list(-93.0 p1_y) list(0.0 p1_y) list(93.0 p1_y))
                p2_vias = list(list(-93.0 p2_y) list(0.0 p2_y) list(93.0 p2_y))
            )
            ( r_int == 90
                p1_x = -355.0
                p2_x =  355.0
                p1_vias = list(list(p1_x -93.0) list(p1_x 0.0) list(p1_x 93.0))
                p2_vias = list(list(p2_x -93.0) list(p2_x 0.0) list(p2_x 93.0))
            )
            ( t ; 270 deg
                p1_x =  355.0
                p2_x = -355.0
                p1_vias = list(list(p1_x -93.0) list(p1_x 0.0) list(p1_x 93.0))
                p2_vias = list(list(p2_x -93.0) list(p2_x 0.0) list(p2_x 93.0))
            )
        )
        list(p1_vias p2_vias)
    )
)

; -----------------------------------------------------------------------------
; 3. 1D & 2D Mixed-Orientation (0 deg + 90 deg) Max-Packing LSC Solver in SKILL
; -----------------------------------------------------------------------------
procedure( pdn_pack_1d_centers_skill(min_edge max_edge item_span pitch)
    let((avail cnt used_span start_c res i)
        avail = float(max_edge) - float(min_edge)
        if( avail < (float(item_span) - 0.01) then
            nil
        else
            cnt = 1 + floor((avail - float(item_span) + 0.01) / float(pitch))
            used_span = float(cnt - 1) * float(pitch) + float(item_span)
            start_c = float(min_edge) + 0.5 * (avail - used_span) + 0.5 * float(item_span)
            res = nil
            for(i 0 (cnt - 1)
                res = append1(res (start_c + float(i) * float(pitch)))
            )
            res
        )
    )
)

procedure( pdn_maximize_0201_lsc_in_pocket_skill(
    w_left w_bot w_right w_top wall_sro_r sro_rule_um bga_rule_um
)
    let((margin sx1 sy1 sx2 sy2 pitch_short pitch_long
         v_xs avail_h n_v_rows used_v_h rem_h can_h_strip v_start_y
         layout_a layout_b r_i c_i cy cx h_cy h_xs h_ys avail_w n_h_cols
         used_h_w rem_w can_v_strip h_start_x v_cx v_ys)

        margin = float(wall_sro_r) + float(bga_rule_um) ; 240 + 500 = 740.0 um
        sx1 = float(w_left)  + margin
        sy1 = float(w_bot)   + margin
        sx2 = float(w_right) - margin
        sy2 = float(w_top)   - margin

        pitch_short = 300.0 + float(sro_rule_um)
        pitch_long  = 820.0 + float(sro_rule_um)

        layout_a = nil
        v_xs = pdn_pack_1d_centers_skill(sx1 sx2 300.0 pitch_short)
        avail_h = sy2 - sy1
        if( v_xs != nil && avail_h >= 820.0 then
            n_v_rows = 1 + floor((avail_h - 820.0 + 0.01) / pitch_long)
            used_v_h = float(n_v_rows - 1) * pitch_long + 820.0
            rem_h    = avail_h - used_v_h
            can_h_strip = (rem_h >= (float(sro_rule_um) + 300.0 - 0.01))
            v_start_y = if( can_h_strip then (sy1 + 410.0) else (sy1 + 0.5 * (avail_h - used_v_h) + 410.0))
            for(r_i 0 (n_v_rows - 1)
                cy = v_start_y + float(r_i) * pitch_long
                c_i = 0
                foreach(cx v_xs
                    layout_a = append1(layout_a list(cx cy if(mod(c_i 2) == 0 then 0.0 else 180.0)))
                    c_i = c_i + 1
                )
            )
            if( can_h_strip then
                h_cy = v_start_y + float(n_v_rows - 1) * pitch_long + 410.0 + float(sro_rule_um) + 150.0
                if( (h_cy + 150.0) <= (sy2 + 1.0) then
                    h_xs = pdn_pack_1d_centers_skill(sx1 sx2 820.0 pitch_long)
                    foreach(cx h_xs
                        layout_a = append1(layout_a list(cx h_cy 90.0))
                    )
                )
            )
        )

        layout_b = nil
        h_ys = pdn_pack_1d_centers_skill(sy1 sy2 300.0 pitch_short)
        avail_w = sx2 - sx1
        if( h_ys != nil && avail_w >= 820.0 then
            n_h_cols = 1 + floor((avail_w - 820.0 + 0.01) / pitch_long)
            used_h_w = float(n_h_cols - 1) * pitch_long + 820.0
            rem_w    = avail_w - used_h_w
            can_v_strip = (rem_w >= (float(sro_rule_um) + 300.0 - 0.01))
            h_start_x = if( can_v_strip then (sx1 + 410.0) else (sx1 + 0.5 * (avail_w - used_h_w) + 410.0))
            for(c_i 0 (n_h_cols - 1)
                cx = h_start_x + float(c_i) * pitch_long
                r_i = 0
                foreach(cy h_ys
                    layout_b = append1(layout_b list(cx cy if(mod(r_i 2) == 0 then 90.0 else 270.0)))
                    r_i = r_i + 1
                )
            )
            if( can_v_strip then
                v_cx = h_start_x + float(n_h_cols - 1) * pitch_long + 410.0 + float(sro_rule_um) + 150.0
                if( (v_cx + 150.0) <= (sx2 + 1.0) then
                    v_ys = pdn_pack_1d_centers_skill(sy1 sy2 820.0 pitch_long)
                    foreach(cy v_ys
                        layout_b = append1(layout_b list(v_cx cy 0.0))
                    )
                )
            )
        )

        if( length(layout_b) > length(layout_a) then layout_b else layout_a)
    )
)

; -----------------------------------------------------------------------------
; 4. Place Single 0201 LSC on BASE + 6 (12B -> BASE) Vias on Pin 1 & Pin 2 Pads
; -----------------------------------------------------------------------------
procedure( pdn_place_single_lsc_and_6vias_skill(
    cx cy rot_deg lsc_sym_name via_ps vdd_dbid vss_dbid @optional (ref_des nil)
)
    let((offs p1_offs p2_offs dx dy vx vy via_cnt sx1 sy1 sx2 sy2
         rdes plc_res sym_obj p1_obj p2_obj vdd_name vss_name)
        axlSetVariable("logic_edit_enabled" t)
        rdes = if( ref_des && ref_des != "" then ref_des else sprintf(nil "C_LSC_%d_%d" round(abs(cx)) round(abs(cy))) )
        let( (cwd dp dev_name dev_file dfp)
            cwd = or(axlGetVariable("cwd") ".")
            dev_name = strcat("LSC_DEV_" lsc_sym_name)
            dev_file = strcat(cwd "/" dev_name ".txt")
            unless( isFile(dev_file)
                dfp = outfile(dev_file "w")
                when( dfp
                    fprintf(dfp "(DEVICE FILE: %s)\nPACKAGE %s\nCLASS DISCRETE\nPINCOUNT 2\nEND\n" dev_name lsc_sym_name)
                    close(dfp)
                )
            )
            dp = or(axlGetVariable("devpath") ".")
            unless( rexMatchp(cwd dp) axlSetVariable("devpath" strcat(cwd " " dp)) )
            errset(axlDBCreateComponent(rdes dev_name lsc_sym_name "DISCRETE") nil)
        )
        plc_res = errset(axlDBCreateSymbol(rdes list(cx cy) nil rot_deg) nil)
        sym_obj = if( plc_res && car(plc_res) then
                      if( listp(car(plc_res)) then car(car(plc_res)) else car(plc_res) )
                  else nil )
        when( sym_obj && sym_obj->pins
            let( (se0)
                se0 = if( car(sym_obj->pins)->startEnd then upperCase(sprintf(nil "%L" car(sym_obj->pins)->startEnd)) else "" )
                unless( rexMatchp("BASE" se0) || rexMatchp("BOTTOM" se0)
                    errset(axlDeleteObject(sym_obj) nil)
                    plc_res = errset(axlDBCreateSymbol(rdes list(cx cy) t rot_deg) nil)
                    sym_obj = if( plc_res && car(plc_res) then
                                  if( listp(car(plc_res)) then car(car(plc_res)) else car(plc_res) )
                              else nil )
                )
            )
        )
        when( sym_obj && sym_obj->pins && length(sym_obj->pins) >= 2
            p1_obj = nth(0 sym_obj->pins)
            p2_obj = nth(1 sym_obj->pins)
            foreach( p sym_obj->pins
                when( p->number == "1" p1_obj = p )
                when( p->number == "2" p2_obj = p )
            )
            vdd_name = if( vdd_dbid && vdd_dbid->name then vdd_dbid->name else "VDDUC0" )
            vss_name = if( vss_dbid && vss_dbid->name then vss_dbid->name else "VSS" )
            errset(axlChangeNet(p1_obj vdd_name) nil)
            errset(axlChangeNet(p2_obj vss_name) nil)
        )
        if( mod(round(float(rot_deg)) 180) == 0 then
            sx1 = cx - 150.0
            sy1 = cy - 410.0
            sx2 = cx + 150.0
            sy2 = cy + 410.0
        else
            sx1 = cx - 410.0
            sy1 = cy - 150.0
            sx2 = cx + 410.0
            sy2 = cy + 150.0
        )
        axlDBCreateRectangle(list(list(sx1 sy1) list(sx2 sy2)) nil "PACKAGE GEOMETRY/PLACE_BOUND_BOTTOM")

        via_cnt = 0
        offs = pdn_get_lsc_pad_via_offsets_skill(rot_deg)
        p1_offs = car(offs)
        p2_offs = cadr(offs)

        if( via_ps != nil then
            foreach(of p1_offs
                vx = cx + car(of)
                vy = cy + cadr(of)
                axlDBCreateVia(via_ps list(vx vy) vdd_dbid)
                via_cnt = via_cnt + 1
            )
            foreach(of p2_offs
                vx = cx + car(of)
                vy = cy + cadr(of)
                axlDBCreateVia(via_ps list(vx vy) vss_dbid)
                via_cnt = via_cnt + 1
            )
        )
        via_cnt
    )
)

; -----------------------------------------------------------------------------
; 5. Master Standalone SKILL Entrypoint for Step 3 (BASE Pockets + BGA Vias)
; -----------------------------------------------------------------------------
procedure( pdn_route_base_lsc_and_bga_full_skill(
    bga_via_option
    sro_to_sro_rule_um
)
    let((cwd report_path d net_tbl vdd_dbid vss_dbid via_ps lsc_sym_name
         pockets pck packed_caps cap cx cy rot
         lsc_cnt lsc_via_cnt bga_ball_cnt bga_via_cnt
         bga_offs syms sym pins pin px py pnet net_dbid dx dy)

        cwd = pdn_get_cwd()
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/base_lsc_bga_skill_report.txt"))

        errset(axlDBControl('drcEnable nil) nil)
        errset(axlDBControl('dynamicFillMode 'disabled) nil)

        d = axlDBGetDesign()
        net_tbl  = pdn_ensure_net_table()
        vdd_dbid = pdn_get_or_create_net(net_tbl "VDDUC0")
        vss_dbid = pdn_get_or_create_net(net_tbl "VSS")
        via_ps   = pdn_resolve_padstack(
            list("V90_65_90_12B_BASE_01A" "V83_55_83_12B_BASE_01A" "V77_49_77_12B_BASE_01A")
        )
        lsc_sym_name = if( float(sro_to_sro_rule_um) <= 180.0 then "SM0201S_690X390X220_01C" else "SM0201_690X390X550_01A")

        ; 8 Learned Empty BGA Pockets under U7: (b_left b_bot b_right b_top wall_sro_r)
        pockets = list(
            list(27678.2 -1175.0 35004.8  1645.0 240.0)
            list(27678.2  9635.0 35004.8 12455.0 240.0)
            list(27678.2 20915.0 35004.8 23735.0 240.0)
            list(13839.1 -3525.0 17909.4  3055.0 240.0)
            list(14653.2 26555.0 17909.4 33135.0 240.0)
            list(19537.5  4935.0 24421.9 14335.0 240.0)
            list(19537.5 18095.0 24421.9 27495.0 240.0)
            list(24421.9 31255.0 34190.7 35485.0 240.0)
        )

        lsc_cnt     = 0
        lsc_via_cnt = 0
        foreach(pck pockets
            packed_caps = pdn_maximize_0201_lsc_in_pocket_skill(
                nth(0 pck) nth(1 pck) nth(2 pck) nth(3 pck) nth(4 pck)
                float(sro_to_sro_rule_um) 500.0
            )
            foreach(cap packed_caps
                cx  = nth(0 cap)
                cy  = nth(1 cap)
                rot = nth(2 cap)
                lsc_cnt = lsc_cnt + 1
                lsc_via_cnt = lsc_via_cnt + pdn_place_single_lsc_and_6vias_skill(
                    cx cy rot lsc_sym_name via_ps vdd_dbid vss_dbid
                )
            )
        )

        ; Place Selected BGA Via Cluster Option on Power/Ground BGA Balls in U7 window
        bga_offs     = pdn_get_bga_via_offsets_skill(bga_via_option)
        bga_ball_cnt = 0
        bga_via_cnt  = 0

        if( d != nil && via_ps != nil then
            foreach(sym d->symbols
                if( sym->refdes == "A1" || rexMatchp("14521" upperCase(if( sym->name != nil then sym->name else ""))) then
                    foreach(pin sym->pins
                        px = if( pin->xy != nil then float(car(pin->xy)) else 0.0)
                        py = if( pin->xy != nil then float(cadr(pin->xy)) else 0.0)
                        if( px >= 13500.0 && px <= 35200.0 && py >= -3800.0 && py <= 35800.0 then
                            pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "")
                            if( pdn_is_pwr_gnd_net(pnet) then
                                bga_ball_cnt = bga_ball_cnt + 1
                                net_dbid = pdn_get_or_create_net(net_tbl pnet)
                                foreach(of bga_offs
                                    dx = car(of)
                                    dy = cadr(of)
                                    axlDBCreateVia(via_ps list((px + dx) (py + dy)) net_dbid)
                                    bga_via_cnt = bga_via_cnt + 1
                                )
                            )
                        )
                    )
                )
            )
        )

        pdn_write_report(
            report_path
            "SUCCESS"
            list(
                list("STAGE" "STEP3_BASE_LSC_BGA_FULL_SKILL")
                list("BGA_VIA_OPTION" bga_via_option)
                list("SRO_TO_SRO_RULE_UM" sprintf(nil "%.1f" float(sro_to_sro_rule_um)))
                list("LSC_CAPS_PLACED" sprintf(nil "%d" lsc_cnt))
                list("LSC_PAD_VIAS_CREATED" sprintf(nil "%d" lsc_via_cnt))
                list("BGA_BALLS_ROUTED" sprintf(nil "%d" bga_ball_cnt))
                list("BGA_CLUSTER_VIAS_CREATED" sprintf(nil "%d" bga_via_cnt))
            )
        )
        printf("[AGENT04-BASE-SKILL] Placed %d 0201 LSCs (%d LSC vias) and %d BGA cluster vias (%s).\n"
            lsc_cnt lsc_via_cnt bga_via_cnt bga_via_option)
        list(lsc_cnt lsc_via_cnt bga_ball_cnt bga_via_cnt)
    )
)

; -----------------------------------------------------------------------------
; 6. High-Speed Pipe-Delimited Recipe Importer (pdn_import_base_lsc_bga_recipe_batch)
; -----------------------------------------------------------------------------
procedure( pdn_import_base_lsc_bga_recipe_batch()
    let((cwd recipe_path report_path save_design in_port line tokens rec_type
         net_tbl pad_tbl default_via_ps
         lsc_cnt lsc_via_cnt bga_via_cnt err_cnt
         kv_tbl sym_name cx cy rot net_name net_dbid ps_name vx vy role)

        cwd = pdn_get_cwd()
        recipe_path = pdn_get_env("PDN_BASE_RECIPE" strcat(cwd "/mockup_BASE_Option2_5Via_Quincunx_recipe.txt"))
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/base_lsc_bga_report.txt"))
        save_design = pdn_get_env_bool("PDN_SAVE_DESIGN" nil)

        errset(axlDBControl('drcEnable nil) nil)
        errset(axlDBControl('dynamicFillMode 'disabled) nil)

        net_tbl = pdn_ensure_net_table()
        pad_tbl = makeTable("pdn_base_pad_tbl" nil)
        default_via_ps = pdn_resolve_padstack(
            list("V90_65_90_12B_BASE_01A" "V83_55_83_12B_BASE_01A" "V77_49_77_12B_BASE_01A")
        )

        lsc_cnt     = 0
        lsc_via_cnt = 0
        bga_via_cnt = 0
        err_cnt     = 0

        in_port = infile(recipe_path)
        if( in_port == nil then
            pdn_write_report(
                report_path
                "ERROR"
                list(
                    list("STAGE" "STEP3_BASE_LSC_BGA_IMPORT")
                    list("MESSAGE" strcat("Cannot open recipe file: " recipe_path))
                )
            )
            nil
        else
            while( gets(line in_port)
                line = car(parseString(line "\r\n"))
                if( line != nil && line != "" && substring(line 1 1) != "#" then
                    tokens = parseString(line "|")
                    if( length(tokens) >= 2 then
                        rec_type = upperCase(car(tokens))
                        case( rec_type
                            ("LSC_SYM"
                                kv_tbl   = pdn_kv_from_tokens(cdr(tokens))
                                sym_name = kv_tbl["SYMBOL"]
                                cx       = float(atof(kv_tbl["X"]))
                                cy       = float(atof(kv_tbl["Y"]))
                                rot      = float(atof(kv_tbl["ROT"]))
                                errset(axlDBCreateSymbol(list(sym_name "LSC") list(cx cy) t rot) nil)
                                axlDBCreateRectangle(
                                    list(list(cx - 150.0 cy - 410.0) list(cx + 150.0 cy + 410.0))
                                    nil "PACKAGE GEOMETRY/PLACE_BOUND_BOTTOM"
                                )
                                lsc_cnt = lsc_cnt + 1
                            )
                            ("VIA"
                                if( length(tokens) >= 7 then
                                    net_name = nth(1 tokens)
                                    ps_name  = nth(2 tokens)
                                    vx       = float(atof(nth(5 tokens)))
                                    vy       = float(atof(nth(6 tokens)))
                                    role     = if( length(tokens) >= 8 then nth(7 tokens) else "VIA")

                                    if( pad_tbl[ps_name] == nil then
                                        if( axlLoadPadstack(ps_name) != nil then
                                            pad_tbl[ps_name] = ps_name
                                        else
                                            pad_tbl[ps_name] = default_via_ps
                                        )
                                    )
                                    net_dbid = pdn_get_or_create_net(net_tbl net_name)
                                    if( pad_tbl[ps_name] != nil then
                                        if( net_dbid != nil then
                                            axlDBCreateVia(pad_tbl[ps_name] list(vx vy) net_dbid)
                                        else
                                            axlDBCreateVia(pad_tbl[ps_name] list(vx vy))
                                        )
                                        if( role == "LSC_PAD_VIA" then
                                            lsc_via_cnt = lsc_via_cnt + 1
                                        else
                                            bga_via_cnt = bga_via_cnt + 1
                                        )
                                    else
                                        err_cnt = err_cnt + 1
                                    )
                                )
                            )
                        )
                    )
                )
            )
            close(in_port)

            if( save_design then
                axlSaveDesign(?design axlCurrentDesign() ?noConfirm t)
            )

            pdn_write_report(
                report_path
                "SUCCESS"
                list(
                    list("STAGE" "STEP3_BASE_LSC_BGA_IMPORT")
                    list("RECIPE_FILE" recipe_path)
                    list("LSC_SYMBOLS_IMPORTED" sprintf(nil "%d" lsc_cnt))
                    list("LSC_PAD_VIAS_IMPORTED" sprintf(nil "%d" lsc_via_cnt))
                    list("BGA_PAD_VIAS_IMPORTED" sprintf(nil "%d" bga_via_cnt))
                    list("ERRORS" sprintf(nil "%d" err_cnt))
                )
            )
            printf("[AGENT04-BASE] Imported %d LSCs, %d LSC vias, and %d BGA vias from %s.\n"
                lsc_cnt lsc_via_cnt bga_via_cnt recipe_path)
            t
        )
    )
)
