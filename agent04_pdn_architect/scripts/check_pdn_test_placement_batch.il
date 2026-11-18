; =============================================================================
; File: check_pdn_test_placement_batch.il
; Package: agent04_pdn_architect
; Description: Headless SKILL extractor for PDN_test.mcm to audit Die Symbol
;              placement (U7, Bridges, HBMs) and eDTC placement against J97403
;              Design Rules.
; =============================================================================

procedure( pdn_extract_pdn_test_placement()
    let((cwd d p_sym p_edtc_pin p_u7_pin p_child p_shape p_rep
         syms sym sym_ref sym_name sym_lyr sx sy srot smir bbo bx1 by1 bx2 by2
         pins pin px py pnum pnet ppad p_cnt
         px1 py1 px2 py2 first_p
         ch_list ch ch_lyr ch_bbo cx1 cy1 cx2 cy2
         u7_pin_cnt edtc_pin_cnt sym_cnt)

        cwd = pdn_get_cwd()
        d = axlDBGetDesign()

        p_sym      = outfile(strcat(cwd "/pdn_test_symbols.csv") "w")
        p_edtc_pin = outfile(strcat(cwd "/pdn_test_edtc_pins.csv") "w")
        p_u7_pin   = outfile(strcat(cwd "/pdn_test_u7_pins_sample.csv") "w")
        p_child    = outfile(strcat(cwd "/pdn_test_symbol_children.csv") "w")
        p_rep      = strcat(cwd "/pdn_test_extract_report.txt")

        fprintf(p_sym "refdes,symbol_name,layer,x_um,y_um,rotation,mirror,sym_bx1,sym_by1,sym_bx2,sym_by2,pin_count,pin_x1,pin_y1,pin_x2,pin_y2\n")
        fprintf(p_edtc_pin "refdes,symbol_name,pin_number,x_um,y_um,net_name,padstack_name,layer\n")
        fprintf(p_u7_pin "refdes,symbol_name,pin_number,x_um,y_um,net_name,padstack_name,layer\n")
        fprintf(p_child "refdes,symbol_name,child_obj_type,child_layer,cx1,cy1,cx2,cy2\n")

        sym_cnt = 0
        edtc_pin_cnt = 0
        u7_pin_cnt = 0

        if( d != nil then
            syms = d->symbols
            foreach(sym syms
                sym_cnt = sym_cnt + 1
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
                p_cnt = length(pins)
                px1 = 0.0
                py1 = 0.0
                px2 = 0.0
                py2 = 0.0
                first_p = t

                foreach(pin pins
                    px = if( pin->xy != nil then float(car(pin->xy)) else 0.0)
                    py = if( pin->xy != nil then float(cadr(pin->xy)) else 0.0)
                    if( first_p then
                        px1 = px
                        py1 = py
                        px2 = px
                        py2 = py
                        first_p = nil
                    else
                        if( px < px1 then px1 = px)
                        if( py < py1 then py1 = py)
                        if( px > px2 then px2 = px)
                        if( py > py2 then py2 = py)
                    )

                    if( rexMatchp("N24792" upperCase(sym_name)) || rexMatchp("EDTC" upperCase(sym_name)) || rexMatchp("4FCO" upperCase(sym_lyr)) then
                        edtc_pin_cnt = edtc_pin_cnt + 1
                        pnum = if( pin->number != nil then sprintf(nil "%L" pin->number) else "0")
                        pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "DUMMY")
                        ppad = if( pin->definition != nil && pin->definition->name != nil then pin->definition->name else "EDTC_PAD")
                        fprintf(p_edtc_pin "%s,%s,%s,%.3f,%.3f,%s,%s,%s\n" sym_ref sym_name pnum px py pnet ppad sym_lyr)
                    )

                    if( sym_ref == "U7" && u7_pin_cnt < 500 then
                        u7_pin_cnt = u7_pin_cnt + 1
                        pnum = if( pin->number != nil then sprintf(nil "%L" pin->number) else "0")
                        pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "DUMMY")
                        ppad = if( pin->definition != nil && pin->definition->name != nil then pin->definition->name else "UBUMP")
                        fprintf(p_u7_pin "%s,%s,%s,%.3f,%.3f,%s,%s,%s\n" sym_ref sym_name pnum px py pnet ppad sym_lyr)
                    )
                )

                fprintf(p_sym "%s,%s,%s,%.3f,%.3f,%.1f,%s,%.3f,%.3f,%.3f,%.3f,%d,%.3f,%.3f,%.3f,%.3f\n"
                    sym_ref sym_name sym_lyr sx sy srot smir bx1 by1 bx2 by2 p_cnt px1 py1 px2 py2)

                ; Extract symbol child bounding boxes (Place_Bound, Body, Silkscreen, Cavity) for U* and eDTC
                if( substring(sym_ref 1 1) == "U" || rexMatchp("N24792" upperCase(sym_name)) || rexMatchp("EDTC" upperCase(sym_name)) then
                    ch_list = sym->children
                    foreach(ch ch_list
                        ch_lyr = if( ch->layer != nil then ch->layer else "NONE")
                        ch_bbo = ch->bBox
                        if( ch_bbo != nil then
                            cx1 = float(caar(ch_bbo))
                            cy1 = float(cadar(ch_bbo))
                            cx2 = float(caadr(ch_bbo))
                            cy2 = float(cadadr(ch_bbo))
                            fprintf(p_child "%s,%s,%s,%s,%.3f,%.3f,%.3f,%.3f\n"
                                sym_ref sym_name sprintf(nil "%L" ch->objType) ch_lyr cx1 cy1 cx2 cy2)
                        )
                    )
                )
            )
        )

        close(p_sym)
        close(p_edtc_pin)
        close(p_u7_pin)
        close(p_child)

        pdn_write_report(
            p_rep
            "SUCCESS"
            list(
                list("TOTAL_SYMBOLS" sprintf(nil "%d" sym_cnt))
                list("EDTC_PINS" sprintf(nil "%d" edtc_pin_cnt))
                list("U7_PINS_SAMPLED" sprintf(nil "%d" u7_pin_cnt))
            )
        )
        t
    )
)
