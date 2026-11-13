; =============================================================================
; File: stage1_full_extractor_batch.il
; Package: agent04_pdn_architect
; Description: Stage 1 Comprehensive Headless .mcm Extractor (O(N) bounded).
;              Extracts from the .mcm design into <cwd>:
;                1. stackup_from_mcm.csv          (All 53 stackup layers & materials)
;                2. refdes_inventory.csv          (All 2,348 placed symbols & RefDes)
;                3. bga_map.csv                   (All 14,521 BGA balls on A1 / BASE)
;                4. edtc_symbols.csv              (All 72 eDTC symbols + 8 fiducials on 4FCO)
;                5. edtc_pin_map.csv              (All 6,048 eDTC pins on 4FCO)
;                6. lsc_placed_map.csv            (All 467 BASE LSCs + 1,741 SURFACE DSCs)
;                7. die_bridge_refdes_summary.csv (All 54 U* Die/HBM/EMIB Bridge RefDes)
;                8. bump_map.csv                  (Sampled SURFACE Die/Bridge bump pins)
;                9. padstacks_from_mcm.csv        (All 105 .mcm padstacks w/ layer spans)
; =============================================================================

procedure( pdn_is_pwr_gnd_net(net_name)
    let((u)
        if( net_name == nil || net_name == "" then
            nil
        else
            u = upperCase(net_name)
            if( rexMatchp("VDD" u) || rexMatchp("VSS" u) || rexMatchp("VCC" u) || rexMatchp("GND" u) then
                t
            else
                nil
            )
        )
    )
)

procedure( pdn_run_stage1_full_extractor()
    let((cwd d xs_idx p_stk p_ref p_bga p_edtc_sym p_edtc_pin
         p_lsc p_die_sum p_bump p_pad p_rep
         syms sym sym_ref sym_name sym_lyr sx sy srot smir bbo bx1 by1 bx2 by2
         pins rem_pins pin pnum px py pnet ppad
         bga_cnt edtc_sym_cnt edtc_pin_cnt lsc_cnt dsc_cnt die_cnt bump_cnt pad_cnt lyr_cnt
         u_pin_cnt u_sample_cnt p1net p2net p1x p1y p2x p2y
         ps_list ps ps_name is_thru start_l end_l drill_d)

        cwd = pdn_get_cwd()
        d = axlDBGetDesign()

        p_stk      = outfile(strcat(cwd "/stackup_from_mcm.csv") "w")
        p_ref      = outfile(strcat(cwd "/refdes_inventory.csv") "w")
        p_bga      = outfile(strcat(cwd "/bga_map.csv") "w")
        p_edtc_sym = outfile(strcat(cwd "/edtc_symbols.csv") "w")
        p_edtc_pin = outfile(strcat(cwd "/edtc_pin_map.csv") "w")
        p_lsc      = outfile(strcat(cwd "/lsc_placed_map.csv") "w")
        p_die_sum  = outfile(strcat(cwd "/die_bridge_refdes_summary.csv") "w")
        p_bump     = outfile(strcat(cwd "/bump_map.csv") "w")
        p_pad      = outfile(strcat(cwd "/padstacks_from_mcm.csv") "w")
        p_rep      = strcat(cwd "/stage1_extraction_report.txt")

        fprintf(p_stk "layer_index,subclass_name,layer_type\n")
        fprintf(p_ref "refdes,symbol_name,comp_category,layer,x_um,y_um,rotation,mirror,bbox_x1,bbox_y1,bbox_x2,bbox_y2,pin_count\n")
        fprintf(p_bga "refdes,pin_number,x_um,y_um,net_name,padstack_name,layer\n")
        fprintf(p_edtc_sym "refdes,symbol_name,layer,x_um,y_um,rotation,mirror,bbox_x1,bbox_y1,bbox_x2,bbox_y2,pin_count\n")
        fprintf(p_edtc_pin "refdes,symbol_name,pin_number,x_um,y_um,net_name,padstack_name,layer\n")
        fprintf(p_lsc "refdes,symbol_name,cap_role,layer,x_um,y_um,rotation,mirror,pin1_net,pin2_net,pin1_x,pin1_y,pin2_x,pin2_y\n")
        fprintf(p_die_sum "refdes,symbol_name,die_category,layer,x_um,y_um,rotation,mirror,bbox_x1,bbox_y1,bbox_x2,bbox_y2,total_pins\n")
        fprintf(p_bump "refdes,symbol_name,pin_number,x_um,y_um,net_name,padstack_name,is_power_ground,layer\n")
        fprintf(p_pad "padstack_name,is_through,start_layer,end_layer,drill_um\n")

        lyr_cnt = 0
        bga_cnt = 0
        edtc_sym_cnt = 0
        edtc_pin_cnt = 0
        lsc_cnt = 0
        dsc_cnt = 0
        die_cnt = 0
        bump_cnt = 0
        pad_cnt = 0

        ; 1. Extract Conductor Stackup Layers
        xs_idx = 0
        foreach(s axlSubclasses("CONDUCTOR")
            xs_idx = xs_idx + 1
            lyr_cnt = lyr_cnt + 1
            fprintf(p_stk "%d,%s,CONDUCTOR\n" xs_idx s)
        )

        ; 2. Extract Symbols, RefDes, BGA Map, eDTC Map, LSC Map, and Bump Map
        if( d != nil then
            syms = d->symbols
            foreach(sym syms
                sym_ref = if( sym->refdes != nil then sym->refdes else "NOREF")
                sym_name = if( sym->name != nil then sym->name else "NOSYM")
                sym_lyr = if( sym->layer != nil then sym->layer else "UNKNOWN")
                sx = if( sym->xy != nil then float(car(sym->xy)) else 0.0)
                sy = if( sym->xy != nil then float(cadr(sym->xy)) else 0.0)
                srot = if( sym->rotation != nil then float(sym->rotation) else 0.0)
                smir = if( sym->isMirrored then "YES" else "NO")
                bbo = sym->bBox
                if( bbo != nil then
                    bx1 = float(caar(bbo))
                    by1 = float(cadar(bbo))
                    bx2 = float(caadr(bbo))
                    by2 = float(cadadr(bbo))
                else
                    bx1 = 0.0
                    by1 = 0.0
                    bx2 = 0.0
                    by2 = 0.0
                )
                pins = sym->pins
                u_pin_cnt = length(pins)

                let((cat_str u_name)
                    u_name = upperCase(sym_name)
                    cat_str = "OTHER"
                    if( sym_ref == "A1" || rexMatchp("14521" u_name) then
                        cat_str = "BGA_ARRAY_BASE"
                    else
                        if( rexMatchp("N24792" u_name) || rexMatchp("EDTC" u_name) || rexMatchp("4FCO" upperCase(sym_lyr)) then
                            cat_str = "EDTC_4FCO"
                        else
                            if( rexMatchp("SM0201" u_name) || rexMatchp("SM0204" u_name) then
                                if( rexMatchp("BASE" upperCase(sym_lyr)) || rexMatchp("BOTTOM" upperCase(sym_lyr)) then
                                    cat_str = "LSC_BASE"
                                else
                                    cat_str = "DSC_SURFACE"
                                )
                            else
                                if( substring(sym_ref 1 1) == "U" then
                                    if( rexMatchp("BRIDGE" u_name) then
                                        cat_str = "EMIB_BRIDGE_SURFACE"
                                    else
                                        if( rexMatchp("HBM" u_name) then
                                            cat_str = "HBM_DIE_SURFACE"
                                        else
                                            cat_str = "MAIN_DIE_SURFACE"
                                        )
                                    )
                                else
                                    cat_str = "MECHANICAL_FIDUCIAL"
                                )
                            )
                        )
                    )

                    fprintf(p_ref "%s,%s,%s,%s,%.3f,%.3f,%.1f,%s,%.3f,%.3f,%.3f,%.3f,%d\n"
                        sym_ref sym_name cat_str sym_lyr sx sy srot smir bx1 by1 bx2 by2 u_pin_cnt)

                    ; Branch A: All 14,521 BGA Balls on A1 (BASE)
                    if( cat_str == "BGA_ARRAY_BASE" then
                        foreach(pin pins
                            bga_cnt = bga_cnt + 1
                            pnum = if( pin->number != nil then sprintf(nil "%L" pin->number) else "0")
                            px = if( pin->xy != nil then float(car(pin->xy)) else 0.0)
                            py = if( pin->xy != nil then float(cadr(pin->xy)) else 0.0)
                            pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "DUMMY")
                            ppad = if( pin->definition != nil && pin->definition->name != nil then pin->definition->name else "BGA_PAD")
                            fprintf(p_bga "%s,%s,%.3f,%.3f,%s,%s,%s\n" sym_ref pnum px py pnet ppad sym_lyr)
                        )
                    )

                    ; Branch B: All 72 4FCO eDTC Symbols + 8 Fiducials & All 6,048 eDTC Pins
                    if( cat_str == "EDTC_4FCO" then
                        edtc_sym_cnt = edtc_sym_cnt + 1
                        fprintf(p_edtc_sym "%s,%s,%s,%.3f,%.3f,%.1f,%s,%.3f,%.3f,%.3f,%.3f,%d\n"
                            sym_ref sym_name sym_lyr sx sy srot smir bx1 by1 bx2 by2 u_pin_cnt)
                        foreach(pin pins
                            edtc_pin_cnt = edtc_pin_cnt + 1
                            pnum = if( pin->number != nil then sprintf(nil "%L" pin->number) else "0")
                            px = if( pin->xy != nil then float(car(pin->xy)) else 0.0)
                            py = if( pin->xy != nil then float(cadr(pin->xy)) else 0.0)
                            pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "DUMMY")
                            ppad = if( pin->definition != nil && pin->definition->name != nil then pin->definition->name else "EDTC_PAD")
                            fprintf(p_edtc_pin "%s,%s,%s,%.3f,%.3f,%s,%s,%s\n" sym_ref sym_name pnum px py pnet ppad sym_lyr)
                        )
                    )

                    ; Branch C: All 467 BASE LSCs & 1,741 SURFACE DSCs
                    if( cat_str == "LSC_BASE" || cat_str == "DSC_SURFACE" then
                        if( cat_str == "LSC_BASE" then lsc_cnt = lsc_cnt + 1 else dsc_cnt = dsc_cnt + 1)
                        p1net = "NC"
                        p2net = "NC"
                        p1x = sx
                        p1y = sy
                        p2x = sx
                        p2y = sy
                        if( pins != nil then
                            pin = car(pins)
                            p1net = if( pin->net != nil && pin->net->name != nil then pin->net->name else "NC")
                            p1x = if( pin->xy != nil then float(car(pin->xy)) else sx)
                            p1y = if( pin->xy != nil then float(cadr(pin->xy)) else sy)
                            if( cdr(pins) != nil then
                                pin = cadr(pins)
                                p2net = if( pin->net != nil && pin->net->name != nil then pin->net->name else "NC")
                                p2x = if( pin->xy != nil then float(car(pin->xy)) else sx)
                                p2y = if( pin->xy != nil then float(cadr(pin->xy)) else sy)
                            )
                        )
                        fprintf(p_lsc "%s,%s,%s,%s,%.3f,%.3f,%.1f,%s,%s,%s,%.3f,%.3f,%.3f,%.3f\n"
                            sym_ref sym_name cat_str sym_lyr sx sy srot smir p1net p2net p1x p1y p2x p2y)
                    )

                    ; Branch D: U* Die / HBM / EMIB Bridge RefDes on SURFACE (Bounded O(1) sample per die)
                    if( cat_str == "MAIN_DIE_SURFACE" || cat_str == "HBM_DIE_SURFACE" || cat_str == "EMIB_BRIDGE_SURFACE" then
                        die_cnt = die_cnt + 1
                        u_sample_cnt = 0
                        rem_pins = pins
                        while( rem_pins != nil && u_sample_cnt < 100
                            pin = car(rem_pins)
                            rem_pins = cdr(rem_pins)
                            u_sample_cnt = u_sample_cnt + 1
                            bump_cnt = bump_cnt + 1
                            pnum = if( pin->number != nil then sprintf(nil "%L" pin->number) else "0")
                            px = if( pin->xy != nil then float(car(pin->xy)) else 0.0)
                            py = if( pin->xy != nil then float(cadr(pin->xy)) else 0.0)
                            pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "DUMMY")
                            ppad = if( pin->definition != nil && pin->definition->name != nil then pin->definition->name else "UBUMP")
                            fprintf(p_bump "%s,%s,%s,%.3f,%.3f,%s,%s,%s,%s\n"
                                sym_ref sym_name pnum px py pnet ppad
                                if( pdn_is_pwr_gnd_net(pnet) then "TRUE" else "FALSE")
                                sym_lyr)
                        )
                        fprintf(p_die_sum "%s,%s,%s,%s,%.3f,%.3f,%.1f,%s,%.3f,%.3f,%.3f,%.3f,%d\n"
                            sym_ref sym_name cat_str sym_lyr sx sy srot smir bx1 by1 bx2 by2 u_pin_cnt)
                    )
                )
            )

            ; 3. Extract Padstacks from .mcm
            ps_list = d->padstacks
            foreach(ps ps_list
                ps_name = ps->name
                if( ps_name != nil then
                    pad_cnt = pad_cnt + 1
                    is_thru = if( ps->isThrough then "TRUE" else "FALSE")
                    start_l = if( ps->startEnd != nil then sprintf(nil "%L" car(ps->startEnd)) else "ALL")
                    end_l = if( ps->startEnd != nil then sprintf(nil "%L" cadr(ps->startEnd)) else "ALL")
                    drill_d = if( ps->drillDiameter != nil then float(ps->drillDiameter) else 0.0)
                    fprintf(p_pad "%s,%s,%s,%s,%.3f\n" ps_name is_thru start_l end_l drill_d)
                )
            )
        )

        close(p_stk)
        close(p_ref)
        close(p_bga)
        close(p_edtc_sym)
        close(p_edtc_pin)
        close(p_lsc)
        close(p_die_sum)
        close(p_bump)
        close(p_pad)

        pdn_write_report(
            p_rep
            "SUCCESS"
            list(
                list("STAGE" "STAGE1_FULL_MCM_EXTRACTOR")
                list("STACKUP_LAYERS" sprintf(nil "%d" lyr_cnt))
                list("TOTAL_SYMBOLS" sprintf(nil "%d" length(d->symbols)))
                list("BGA_PINS_EXTRACTED" sprintf(nil "%d" bga_cnt))
                list("EDTC_SYMBOLS_EXTRACTED" sprintf(nil "%d" edtc_sym_cnt))
                list("EDTC_PINS_EXTRACTED" sprintf(nil "%d" edtc_pin_cnt))
                list("LSC_BASE_CAPS_EXTRACTED" sprintf(nil "%d" lsc_cnt))
                list("DSC_SURFACE_CAPS_EXTRACTED" sprintf(nil "%d" dsc_cnt))
                list("DIE_BRIDGE_REFDES_EXTRACTED" sprintf(nil "%d" die_cnt))
                list("BUMP_PINS_EXTRACTED" sprintf(nil "%d" bump_cnt))
                list("PADSTACKS_EXTRACTED" sprintf(nil "%d" pad_cnt))
            )
        )
        printf("[AGENT04-STAGE1] Extraction complete: %d BGA pins, %d eDTC symbols (%d pins), %d LSCs, %d Dies/Bridges (%d bumps), %d padstacks.\n"
            bga_cnt edtc_sym_cnt edtc_pin_cnt lsc_cnt die_cnt bump_cnt pad_cnt)
        t
    )
)
