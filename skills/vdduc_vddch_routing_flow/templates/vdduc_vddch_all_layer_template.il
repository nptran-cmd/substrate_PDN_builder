; =============================================================================
; vdduc_vddch_all_layer_template.il
; Reusable Cadence APD / Allegro SKILL All-Layer Importer Template for
; VDDUC* (U5..U8 LDB) and VDDCH* (U1..U4 LDC) + VSS 27-Layer PDN Routing Flow.
;
; Key Safeguards:
;   1. Uses O(1) SKILL `makeTable` net/padstack caches & line-by-line `gets`
;      streaming so 170,000+ objects never trigger SKILL stack overflow.
;   2. Creates filled conductor planes (`isFilled = t`) via `axlDBCreateOpenShape`
;      + `axlDBCreateVoid` (`12F/11F/10F` EMIB Cavity/Guard-Ring/CSB KOZs and
;      `4FCO..4BCO` eDTC KOZs) + `axlDBCreateCloseShape` before advancing layers.
;   3. Draws `SUBSTRATE GEOMETRY/LSC_CAVITY` (`R=500 um`, EMIB Rule #19 shadow
;      clipped) + `ROUTE KEEPOUT/BASE` (`Code D` 178 um Cu/Signal KOZ) on `BASE`.
; =============================================================================

procedure( pdnRunVdducVddchMasterRecipe( recipePath outMcmPath reportPath )
  let( (inPort rawLine line fields recType netTbl padTbl openPlane countVia countCline
        countLsc countPlane countVoid countCav errCount netDb padDb symDb
        x1 y1 x2 y2 cx cy rot rCav kozExt poly p1 p2 subclass)

    netTbl = makeTable("pdnNetCache" nil)
    padTbl = makeTable("pdnPadCache" nil)
    openPlane = nil
    countVia = 0
    countCline = 0
    countLsc = 0
    countPlane = 0
    countVoid = 0
    countCav = 0
    errCount = 0

    inPort = infile(recipePath)
    unless(inPort
      error("pdnRunVdducVddchMasterRecipe: Cannot open recipe file %s" recipePath)
    )

    while( gets(rawLine inPort)
      line = buildString(parseString(rawLine "\r\n") "")
      when( strlen(line) > 0 && substring(line 1 1) != "#"
        fields = parseString(line "|")
        recType = car(fields)

        ; Close any pending open plane before non-void records
        when( openPlane && recType != "PLANE_VOID"
          axlDBCreateCloseShape(openPlane)
          openPlane = nil
        )

        cond(
          ( recType == "PLANE"
            let( (netName lyrName netObj rpath)
              netName = nth(1 fields)
              lyrName = strcat("CONDUCTOR/" nth(2 fields))
              x1 = atof(nth(3 fields))
              y1 = atof(nth(4 fields))
              x2 = atof(nth(5 fields))
              y2 = atof(nth(6 fields))
              netObj = netTbl[netName]
              unless(netObj
                netObj = axlDBCreateNet(netName)
                netTbl[netName] = netObj
              )
              rpath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1))
              openPlane = axlDBCreateOpenShape(rpath t lyrName netName)
              if( openPlane then countPlane++ else errCount++ )
            )
          )

          ( recType == "PLANE_VOID"
            when( openPlane
              let( (vpath)
                x1 = atof(nth(2 fields))
                y1 = atof(nth(3 fields))
                x2 = atof(nth(4 fields))
                y2 = atof(nth(5 fields))
                vpath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1))
                if( axlDBCreateVoid(openPlane vpath) then countVoid++ else errCount++ )
              )
            )
          )

          ( recType == "CAVITY_OUTLINE"
            let( (cpath kpath)
              x1 = atof(nth(2 fields))
              y1 = atof(nth(3 fields))
              x2 = atof(nth(4 fields))
              y2 = atof(nth(5 fields))
              rCav = atof(nth(6 fields))
              kozExt = atof(nth(7 fields))
              ; Rounded-corner LSC_CAVITY path (R = 500 um @ 4 corners)
              cpath = axlPathStart(list((x1 + rCav):y1))
              axlPathLine(cpath 0.0 (x2 - rCav):y1)
              axlPathArcCenter(cpath 0.0 x2:(y1 + rCav) nil (x2 - rCav):(y1 + rCav))
              axlPathLine(cpath 0.0 x2:(y2 - rCav))
              axlPathArcCenter(cpath 0.0 (x2 - rCav):y2 nil (x2 - rCav):(y2 - rCav))
              axlPathLine(cpath 0.0 (x1 + rCav):y2)
              axlPathArcCenter(cpath 0.0 x1:(y2 - rCav) nil (x1 + rCav):(y2 - rCav))
              axlPathLine(cpath 0.0 x1:(y1 + rCav))
              axlPathArcCenter(cpath 0.0 (x1 + rCav):y1 nil (x1 + rCav):(y1 + rCav))
              axlDBCreatePath(cpath "SUBSTRATE GEOMETRY/LSC_CAVITY")
              ; External 178 um Code D Non-SMT Cu/Signal Keepout on ROUTE KEEPOUT/BASE
              kpath = axlPathStart(list((x1 - kozExt):(y1 - kozExt) (x2 + kozExt):(y1 - kozExt)
                                        (x2 + kozExt):(y2 + kozExt) (x1 - kozExt):(y2 + kozExt)
                                        (x1 - kozExt):(y1 - kozExt)))
              axlDBCreateShape(kpath t "ROUTE KEEPOUT/BASE" nil)
              countCav++
            )
          )

          ( recType == "LSC_SYM"
            let( (refDes symName p1Net p2Net resSym symObj pinObjs p1Obj p2Obj)
              axlSetVariable("logic_edit_enabled" t)
              refDes = nth(1 fields)
              symName = nth(2 fields)
              cx = atof(nth(3 fields))
              cy = atof(nth(4 fields))
              rot = atof(nth(5 fields))
              p1Net = nth(7 fields)
              p2Net = nth(8 fields)
              unless( netTbl[p1Net] netTbl[p1Net] = or(axlDBFindByName('net p1Net) axlDBCreateNet(p1Net)) )
              unless( netTbl[p2Net] netTbl[p2Net] = or(axlDBFindByName('net p2Net) axlDBCreateNet(p2Net)) )
              let( (cwd dp devName devFile dfp)
                cwd = or(axlGetVariable("cwd") ".")
                devName = strcat("LSC_DEV_" symName)
                devFile = strcat(cwd "/" devName ".txt")
                unless( isFile(devFile)
                  dfp = outfile(devFile "w")
                  when( dfp
                    fprintf(dfp "(DEVICE FILE: %s)\nPACKAGE %s\nCLASS DISCRETE\nPINCOUNT 2\nEND\n" devName symName)
                    close(dfp)
                  )
                )
                dp = or(axlGetVariable("devpath") ".")
                unless( rexMatchp(cwd dp) axlSetVariable("devpath" strcat(cwd " " dp)) )
                errset(axlDBCreateComponent(refDes devName symName "DISCRETE") nil)
              )
              resSym = errset(axlDBCreateSymbol(refDes cx:cy nil rot) nil)
              symObj = if( resSym && car(resSym) then
                         if( listp(car(resSym)) then car(car(resSym)) else car(resSym) )
                       else nil )
              when( symObj && symObj->pins
                let( (se0)
                  se0 = if( car(symObj->pins)->startEnd then upperCase(sprintf(nil "%L" car(symObj->pins)->startEnd)) else "" )
                  unless( rexMatchp("BASE" se0) || rexMatchp("BOTTOM" se0)
                    errset(axlDeleteObject(symObj) nil)
                    resSym = errset(axlDBCreateSymbol(refDes cx:cy t rot) nil)
                    symObj = if( resSym && car(resSym) then
                               if( listp(car(resSym)) then car(car(resSym)) else car(resSym) )
                             else nil )
                  )
                )
              )
              if( symObj then
                countLsc++
                pinObjs = symObj->pins
                when( pinObjs && length(pinObjs) >= 2
                  p1Obj = nth(0 pinObjs)
                  p2Obj = nth(1 pinObjs)
                  foreach( pObj pinObjs
                    when( pObj->number == "1" p1Obj = pObj )
                    when( pObj->number == "2" p2Obj = pObj )
                  )
                  errset(axlChangeNet(p1Obj p1Net) nil)
                  errset(axlChangeNet(p2Obj p2Net) nil)
                )
              else
                errCount++
              )
            )
          )

          ( recType == "VIA"
            let( (netName padName lStart lEnd vx vy padObj viaRes)
              netName = nth(1 fields)
              padName = nth(2 fields)
              vx = atof(nth(5 fields))
              vy = atof(nth(6 fields))
              padObj = padTbl[padName]
              unless(padObj
                padObj = axlLoadPadstack(padName)
                padTbl[padName] = padObj
              )
              if( padObj then
                viaRes = axlDBCreateVia(padObj vx:vy netName nil 0.0 nil)
                if( car(viaRes) then countVia++ else errCount++ )
              else
                errCount++
              )
            )
          )

          ( recType == "CLINE"
            let( (netName lyrSub wUm lx1 ly1 lx2 ly2 clRes)
              netName = nth(1 fields)
              lyrSub = strcat("CONDUCTOR/" nth(2 fields))
              wUm = atof(nth(3 fields))
              lx1 = atof(nth(4 fields))
              ly1 = atof(nth(5 fields))
              lx2 = atof(nth(6 fields))
              ly2 = atof(nth(7 fields))
              clRes = axlDBCreateLine(list(lx1:ly1 lx2:ly2) wUm lyrSub netName)
              if( clRes then countCline++ else errCount++ )
            )
          )
        )
      )
    )

    when( openPlane
      axlDBCreateCloseShape(openPlane)
      openPlane = nil
    )
    close(inPort)

    axlDBRefreshId(nil)
    when( outMcmPath && strlen(outMcmPath) > 0
      axlSaveDesign(?design outMcmPath ?noConfirm t)
    )

    when( reportPath && strlen(reportPath) > 0
      let( (rp)
        rp = outfile(reportPath "w")
        fprintf(rp "STATUS=SUCCESS\nPLANES=%d\nPLANE_VOIDS=%d\nCAVITIES=%d\nLSC_SYMBOLS=%d\nVIAS=%d\nCLINES=%d\nERRORS=%d\n"
                countPlane countVoid countCav countLsc countVia countCline errCount)
        close(rp)
      )
    )
    t
  )
)
