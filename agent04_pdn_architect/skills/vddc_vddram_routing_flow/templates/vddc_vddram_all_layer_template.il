; =============================================================================
; vddc_vddram_all_layer_template.il
; Reusable Multi-Rail Cadence APD / Allegro SKILL All-Layer Importer Template
; for LDA Compute Dies (U9, U12, U88, U10): VDDC* + VDD_0P8_SRAM_CC* + VSS
; + Kelvin Sense Pairs across all 27 substrate layers (SURFACE L01 .. BASE L27).
;
; Supports:
;   - Dedicated planes (`PLANE`) + `12F/11F/10F` EMIB Cavity/Guard-Ring/CSB KOZs,
;     `4FCO..4BCO` `eDTC` KOZs & Split-Island cutouts (`PLANE_VOID`)
;   - Co-planar carved `VDD_0P8_SRAM_CC*` voltage islands (`PLANE_ISLAND`)
;   - `SUBSTRATE GEOMETRY/LSC_CAVITY` (R=500 um, EMIB Rule #19 shadow clipped)
;     + `ROUTE KEEPOUT/BASE` (`Code D` 178 um Ext Cu/Signal KOZ)
;   - Co-pocket `VDDC*` & `SRAM*` `0201` LSC symbols on `BASE`
;   - Multi-rail `VIA` (`V83_55_83`, `8-via` R=195um BGA rings) & `CLINE` records
; =============================================================================

procedure( pdnParseCurvedVertsLda( vertStr )
  let( (pts firstPt xy x y)
    pts = nil
    firstPt = nil
    foreach( p parseString(vertStr ";")
      xy = parseString(p ",")
      when( length(xy) >= 2
        x = float(atof(nth(0 xy)))
        y = float(atof(nth(1 xy)))
        unless( firstPt firstPt = list(x y) )
        pts = append1(pts list(x y))
      )
    )
    when( firstPt && length(pts) >= 3 pts = append1(pts firstPt) )
    pts
  )
)

procedure( pdnRunVddcVddramMasterRecipe( recipePath outMcmPath reportPath )
  let( (inPort rawLine line fields recType netTbl padTbl openPlane
        countPlane countIsland countVoid countCav countLsc countVia countCline errCount
        x1 y1 x2 y2 cx cy rot rCav kozExt)

    netTbl = makeTable("ldaNetCache" nil)
    padTbl = makeTable("ldaPadCache" nil)
    openPlane = nil
    countPlane = 0
    countIsland = 0
    countVoid = 0
    countCav = 0
    countLsc = 0
    countVia = 0
    countCline = 0
    errCount = 0

    inPort = infile(recipePath)
    unless(inPort
      error("pdnRunVddcVddramMasterRecipe: Cannot open recipe file %s" recipePath)
    )

    while( gets(rawLine inPort)
      line = buildString(parseString(rawLine "\r\n") "")
      when( strlen(line) > 0 && substring(line 1 1) != "#"
        fields = parseString(line "|")
        recType = car(fields)

        when( openPlane && recType != "PLANE_VOID"
          axlDBCreateCloseShape(openPlane)
          openPlane = nil
        )

        cond(
          ( recType == "PLANE" || recType == "PLANE_ISLAND"
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
              if( openPlane then
                if( recType == "PLANE" then countPlane++ else countIsland++ )
              else
                errCount++
              )
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
              kpath = axlPathStart(list((x1 - kozExt):(y1 - kozExt) (x2 + kozExt):(y1 - kozExt)
                                        (x2 + kozExt):(y2 + kozExt) (x1 - kozExt):(y2 + kozExt)
                                        (x1 - kozExt):(y1 - kozExt)))
              axlDBCreateShape(kpath t "ROUTE KEEPOUT/BASE" nil)
              countCav++
            )
          )

          ( recType == "POLY_CAVITY" && length(fields) >= 3
            let( (cavPts kozPts safePts rLyr oShp)
              rLyr = "SUBSTRATE GEOMETRY/recess_cavity_pdn"
              unless( axlIsLayer(rLyr) axlLayerCreateNonConductor(rLyr) )
              unless( axlIsLayer("SUBSTRATE GEOMETRY/LSC_CAVITY") axlLayerCreateNonConductor("SUBSTRATE GEOMETRY/LSC_CAVITY") )
              cavPts  = pdnParseCurvedVertsLda(nth(2 fields))
              kozPts  = if( length(fields) >= 4 then pdnParseCurvedVertsLda(nth(3 fields)) else nil )
              safePts = if( length(fields) >= 5 then pdnParseCurvedVertsLda(nth(4 fields)) else nil )
              when( cavPts && length(cavPts) >= 4
                axlDBCreateShape(axlPathStart(cavPts 0.0) t "SUBSTRATE GEOMETRY/LSC_CAVITY")
                axlDBCreatePath(axlPathStart(cavPts 25.0) rLyr)
                countCav++
              )
              when( kozPts && length(kozPts) >= 4 && cavPts && length(cavPts) >= 4
                oShp = car(errset(axlDBCreateOpenShape(axlPathStart(kozPts 0.0) t rLyr nil) nil))
                when( oShp errset(axlDBCreateVoid(oShp axlPathStart(cavPts 0.0)) nil) errset(axlDBCreateCloseShape(oShp) nil) )
                axlDBCreatePath(axlPathStart(kozPts 25.0) rLyr)
                when( axlIsLayer("ROUTE KEEPOUT/BASE") axlDBCreateShape(axlPathStart(kozPts 0.0) t "ROUTE KEEPOUT/BASE") )
              )
              when( safePts && length(safePts) >= 4 && cavPts && length(cavPts) >= 4
                oShp = car(errset(axlDBCreateOpenShape(axlPathStart(cavPts 0.0) t rLyr nil) nil))
                when( oShp errset(axlDBCreateVoid(oShp axlPathStart(safePts 0.0)) nil) errset(axlDBCreateCloseShape(oShp) nil) )
                axlDBCreatePath(axlPathStart(safePts 20.0) rLyr)
              )
            )
          )

          ( recType == "LSC_SYM" || recType == "LSC_PLACE"
            let( (refDes symName p1Net p2Net resSym symObj pinObjs p1Obj p2Obj isPlace)
              axlSetVariable("logic_edit_enabled" t)
              isPlace = (recType == "LSC_PLACE")
              refDes  = nth(1 fields)
              symName = nth(2 fields)
              cx      = atof(nth(3 fields))
              cy      = atof(nth(4 fields))
              rot     = atof(nth(5 fields))
              p1Net   = nth(if( isPlace then 6 else 7 ) fields)
              p2Net   = nth(if( isPlace then 7 else 8 ) fields)
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
            let( (netName padName vx vy padObj viaRes)
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
        fprintf(rp "STATUS=SUCCESS\nPLANES=%d\nISLANDS=%d\nPLANE_VOIDS=%d\nCAVITIES=%d\nLSC_SYMBOLS=%d\nVIAS=%d\nCLINES=%d\nERRORS=%d\n"
                countPlane countIsland countVoid countCav countLsc countVia countCline errCount)
        close(rp)
      )
    )
    t
  )
)
