; =============================================================================
; apd_fast_27layer_template_importer.il
; High-Speed Headless Cadence APD 25.1 Importer for 27-Layer PDN Recipes
; Key Optimization:
;   1. Recipe streams VIA and CLINE before POLY_SHAPE (zero dynamic shape
;      overhead during via/cline creation).
;   2. Uses axlShapeChangeDynamicType(shpObj t nil) (defer dynamic pour)
;      during shape creation, followed by a single batch axlShapeDynamicUpdate(nil t)
;      at the end.
; =============================================================================

procedure( pdnFastTrim(s)
  let( (len startIdx endIdx ch)
    if( stringp(s) then
      len = strlen(s)
      startIdx = 1
      while( (startIdx <= len && member(substring(s startIdx 1) '(" " "\t" "\r" "\n")))
        startIdx = startIdx + 1
      )
      endIdx = len
      while( (endIdx >= startIdx && member(substring(s endIdx 1) '(" " "\t" "\r" "\n")))
        endIdx = endIdx - 1
      )
      if( endIdx >= startIdx then
        substring(s startIdx (endIdx - startIdx + 1))
      else
        ""
      )
    else
      ""
    )
  )
)

procedure( pdnFastParsePts(ptsStr)
  let( (tokens pts tok xy xVal yVal)
    tokens = parseString(ptsStr ";")
    pts = nil
    foreach( tok tokens
      tok = pdnFastTrim(tok)
      when( strlen(tok) > 0
        xy = parseString(tok ",")
        when( length(xy) >= 2
          xVal = atof(car(xy))
          yVal = atof(cadr(xy))
          pts = cons((xVal:yVal) pts)
        )
      )
    )
    reverse(pts)
  )
)

procedure( pdnFastEnsureNet(netName)
  let( (netObj)
    if( ( !netName || netName == "" || netName == "DUMMY" || netName == "NONE" ) then
      nil
    else
      netObj = axlDBFindByName('net netName)
      unless( netObj
        netObj = car(errset(axlDBCreateNet(netName) nil))
      )
      netObj
    )
  )
)

procedure( pdnFastDeleteLsc(refDes)
  let( (sym comp ok)
    ok = nil
    sym = axlDBFindByName('symbol refDes)
    when( sym
      errset(axlDeleteObject(sym) nil)
      ok = t
    )
    comp = axlDBFindByName('component refDes)
    when( comp
      errset(axlDeleteObject(comp) nil)
      ok = t
    )
    ok
  )
)

procedure( pdnFastEnsureDeviceFile(devType symName)
  let( (devFile p)
    devFile = strcat(devType ".txt")
    unless( isFile(devFile)
      p = outfile(devFile "w")
      when( p
        fprintf(p "(Device File: %s)\n" devType)
        fprintf(p "PACKAGE %s\n" symName)
        fprintf(p "CLASS DISCRETE\n")
        fprintf(p "PINCOUNT 2\n")
        fprintf(p "END\n")
        close(p)
      )
    )
    devFile
  )
)

procedure( pdnFastPlaceBaseLsc(refDes symName x y rotDeg vddNet vssNet)
  let( (devClean symClean symObj pins samplePin se isBase compCreated p pinNum targetNetObj)
    symClean = upperCase(pdnFastTrim(symName))
    devClean = strcat("LSC_DEV_" symClean)
    pdnFastEnsureDeviceFile(devClean symClean)

    pdnFastDeleteLsc(refDes)

    compCreated = car(errset(axlDBCreateComponent(refDes devClean symClean) nil))
    symObj = car(errset(axlDBCreateSymbol(list(refDes symClean) x:y nil rotDeg) nil))
    unless( symObj
      symObj = car(errset(axlDBCreateSymbol(symClean x:y nil rotDeg) nil))
    )

    when( symObj
      pins = symObj->pins
      when( pins
        samplePin = car(pins)
        se = samplePin->startEnd
        isBase = (se && car(se) == "CONDUCTOR/BASE")
        unless( isBase
          errset(axlDeleteObject(symObj) nil)
          unless( compCreated
            compCreated = car(errset(axlDBCreateComponent(refDes devClean symClean) nil))
          )
          symObj = car(errset(axlDBCreateSymbol(list(refDes symClean) x:y t rotDeg) nil))
          unless( symObj
            symObj = car(errset(axlDBCreateSymbol(symClean x:y t rotDeg) nil))
          )
        )
      )
    )

    when( symObj
      vddObj = pdnFastEnsureNet(vddNet)
      vssObj = pdnFastEnsureNet(vssNet)
      foreach( p symObj->pins
        pinNum = pdnFastTrim(sprintf(nil "%L" p->number))
        pinNum = pdnFastTrim(car(parseString(pinNum "\"")))
        if( (pinNum == "1" || pinNum == "A" || pinNum == "P1") then
          targetNetObj = vddObj
        else
          targetNetObj = vssObj
        )
        when( targetNetObj
          errset(axlChangeNet(p targetNetObj) nil)
        )
      )
    )
    symObj
  )
)

procedure( pdnFastLogProgress(progFile msg)
  let( (pp)
    pp = outfile(progFile "a")
    when( pp
      fprintf(pp "%s\n" msg)
      close(pp)
    )
  )
)

procedure( pdnFastRunUnified27LayerImport(recipeFile reportFile)
  let( (inPort outPort progFile rawLine line parts cmdType
        curOpenShp curDynBndry curShapeMode curShapeLayer curShapeNet
        polyCnt dynPolyCnt staticPolyCnt voidCnt cavCnt lscDelCnt lscPlaceCnt viaCnt clineCnt errCnt
        netName layerSub shapeMode ptsStr ptsList netObj rpath shpObj
        refDes symName xVal yVal rotVal vddNet vssNet padName startLayer endLayer wStr res
        designPath allNets auditedNets nObj bCnt vCnt sCnt cCnt)

    progFile = strcat(reportFile ".progress")
    inPort = infile(recipeFile)
    if( !inPort then
      outPort = outfile(reportFile "w")
      when( outPort
        fprintf(outPort "STATUS=ERROR\nMESSAGE=Cannot open recipe file %s\n" recipeFile)
        close(outPort)
      )
      nil
    else
      curOpenShp = nil
      curDynBndry = nil
      curShapeMode = ""
      curShapeLayer = ""
      curShapeNet = ""

      polyCnt = 0
      dynPolyCnt = 0
      staticPolyCnt = 0
      voidCnt = 0
      cavCnt = 0
      lscDelCnt = 0
      lscPlaceCnt = 0
      viaCnt = 0
      clineCnt = 0
      errCnt = 0
      auditedNets = makeTable("auditedNets" nil)

      pdnFastLogProgress(progFile "START_IMPORT")

      while( gets(rawLine inPort)
        line = pdnFastTrim(rawLine)
        when( (strlen(line) > 0 && substring(line 1 1) != "#")
          parts = parseString(line "|")
          when( parts
            cmdType = pdnFastTrim(car(parts))
            cond(
              ((equal cmdType "POLY_CAVITY")
                layerSub = pdnFastTrim(nth(1 parts))
                ptsStr = pdnFastTrim(nth(2 parts))
                ptsList = pdnFastParsePts(ptsStr)
                when( length(ptsList) >= 3
                  rpath = axlPathStart(ptsList 0.0)
                  shpObj = car(errset(axlDBCreateShape(rpath t layerSub nil nil) nil))
                  if( shpObj then
                    cavCnt = cavCnt + 1
                  else
                    errCnt = errCnt + 1
                  )
                )
              )

              ((equal cmdType "LSC_DELETE")
                refDes = pdnFastTrim(nth(1 parts))
                if( pdnFastDeleteLsc(refDes) then
                  lscDelCnt = lscDelCnt + 1
                )
              )

              ((equal cmdType "LSC_PLACE")
                refDes = pdnFastTrim(nth(1 parts))
                symName = pdnFastTrim(nth(2 parts))
                xVal = atof(pdnFastTrim(nth(3 parts)))
                yVal = atof(pdnFastTrim(nth(4 parts)))
                rotVal = atof(pdnFastTrim(nth(5 parts)))
                vddNet = pdnFastTrim(nth(6 parts))
                vssNet = pdnFastTrim(nth(7 parts))
                auditedNets[vddNet] = t
                auditedNets[vssNet] = t
                if( pdnFastPlaceBaseLsc(refDes symName xVal yVal rotVal vddNet vssNet) then
                  lscPlaceCnt = lscPlaceCnt + 1
                else
                  errCnt = errCnt + 1
                )
              )

              ((equal cmdType "VIA")
                netName = pdnFastTrim(nth(1 parts))
                padName = pdnFastTrim(nth(2 parts))
                xVal = atof(pdnFastTrim(nth(3 parts)))
                yVal = atof(pdnFastTrim(nth(4 parts)))
                auditedNets[netName] = t
                netObj = pdnFastEnsureNet(netName)
                res = errset(axlDBCreateVia(padName xVal:yVal netObj nil 0.0 nil) nil)
                if( (res && car(res)) then
                  viaCnt = viaCnt + 1
                  when( mod(viaCnt 50000) == 0
                    pdnFastLogProgress(progFile sprintf(nil "PROGRESS cav=%d lsc=%d via=%d cline=%d poly=%d err=%d" cavCnt lscPlaceCnt viaCnt clineCnt polyCnt errCnt))
                  )
                else
                  errCnt = errCnt + 1
                )
              )

              ((equal cmdType "CLINE")
                netName = pdnFastTrim(nth(1 parts))
                layerSub = pdnFastTrim(nth(2 parts))
                wStr = pdnFastTrim(nth(3 parts))
                ptsStr = pdnFastTrim(nth(4 parts))
                auditedNets[netName] = t
                ptsList = pdnFastParsePts(ptsStr)
                when( length(ptsList) >= 2
                  netObj = pdnFastEnsureNet(netName)
                  rpath = axlPathStart(ptsList atof(wStr))
                  res = errset(axlDBCreateLine(rpath atof(wStr) strcat("CONDUCTOR/" layerSub) netObj nil) nil)
                  if( (res && car(res)) then
                    clineCnt = clineCnt + 1
                    when( mod(clineCnt 10000) == 0
                      pdnFastLogProgress(progFile sprintf(nil "PROGRESS cav=%d lsc=%d via=%d cline=%d poly=%d err=%d" cavCnt lscPlaceCnt viaCnt clineCnt polyCnt errCnt))
                    )
                  else
                    errCnt = errCnt + 1
                  )
                )
              )

              ((equal cmdType "POLY_SHAPE")
                when( curOpenShp
                  errset(axlDBCreateCloseShape(curOpenShp) nil)
                  curOpenShp = nil
                  curDynBndry = nil
                )
                netName = pdnFastTrim(nth(1 parts))
                layerSub = pdnFastTrim(nth(2 parts))
                shapeMode = pdnFastTrim(nth(3 parts))
                ptsStr = pdnFastTrim(nth(4 parts))
                auditedNets[netName] = t
                ptsList = pdnFastParsePts(ptsStr)
                when( length(ptsList) >= 3
                  rpath = axlPathStart(ptsList 0.0)
                  netObj = pdnFastEnsureNet(netName)
                  curShapeMode = shapeMode
                  curShapeLayer = strcat("CONDUCTOR/" layerSub)
                  curShapeNet = netName
                  if( equal(shapeMode "DYNAMIC") then
                    shpObj = car(errset(axlDBCreateShape(rpath t curShapeLayer netName nil) nil))
                    if( shpObj then
                      ; Defer dynamic pour (3rd arg = nil) until all shapes & voids are created
                      curDynBndry = car(errset(axlShapeChangeDynamicType(shpObj t nil) nil))
                      curOpenShp = nil
                      polyCnt = polyCnt + 1
                      dynPolyCnt = dynPolyCnt + 1
                    else
                      errCnt = errCnt + 1
                    )
                  else
                    curOpenShp = car(errset(axlDBCreateOpenShape(rpath t curShapeLayer netName nil) nil))
                    curDynBndry = nil
                    if( curOpenShp then
                      polyCnt = polyCnt + 1
                      staticPolyCnt = staticPolyCnt + 1
                    else
                      errCnt = errCnt + 1
                    )
                  )
                  when( mod(polyCnt 100) == 0
                    pdnFastLogProgress(progFile sprintf(nil "PROGRESS cav=%d lsc=%d via=%d cline=%d poly=%d err=%d" cavCnt lscPlaceCnt viaCnt clineCnt polyCnt errCnt))
                  )
                )
              )

              ((equal cmdType "POLY_VOID")
                ptsStr = pdnFastTrim(nth(1 parts))
                ptsList = pdnFastParsePts(ptsStr)
                when( length(ptsList) >= 3
                  rpath = axlPathStart(ptsList 0.0)
                  if( curDynBndry then
                    when( car(errset(axlDBCreateShape(rpath t strcat("ETCH/" cadr(parseString(curShapeLayer "/"))) curShapeNet curDynBndry) nil))
                      voidCnt = voidCnt + 1
                    )
                  else
                    when( curOpenShp
                      when( car(errset(axlDBCreateVoid(curOpenShp rpath) nil))
                        voidCnt = voidCnt + 1
                      )
                    )
                  )
                )
              )

              ((equal cmdType "POLY_CLOSE")
                when( curOpenShp
                  errset(axlDBCreateCloseShape(curOpenShp) nil)
                  curOpenShp = nil
                )
                curDynBndry = nil
              )
            )
          )
        )
      )
      close(inPort)

      when( curOpenShp
        errset(axlDBCreateCloseShape(curOpenShp) nil)
        curOpenShp = nil
      )

      pdnFastLogProgress(progFile sprintf(nil "IMPORT_LOOP_DONE poly=%d (dyn=%d static=%d) cav=%d lsc=%d via=%d cline=%d err=%d -> saving pre-pour checkpoint" polyCnt dynPolyCnt staticPolyCnt cavCnt lscPlaceCnt viaCnt clineCnt errCnt))

      designPath = axlGetDrawingName()
      errset(axlSaveDesign(?design designPath ?noConfirm t) nil)
      pdnFastLogProgress(progFile "PRE_POUR_SAVED -> running axlShapeDynamicUpdate(nil t)")

      errset(axlShapeDynamicUpdate(nil t) nil)
      pdnFastLogProgress(progFile "DYNAMIC_POUR_DONE -> saving final .mcm")

      errset(axlSaveDesign(?design designPath ?noConfirm t) nil)
      pdnFastLogProgress(progFile "FINAL_SAVED")

      outPort = outfile(reportFile "w")
      when( outPort
        fprintf(outPort "STATUS=SUCCESS\n")
        fprintf(outPort "DESIGN=%s\n" designPath)
        fprintf(outPort "POLYGONS_TOTAL=%d\n" polyCnt)
        fprintf(outPort "DYNAMIC_PLANES=%d\n" dynPolyCnt)
        fprintf(outPort "STATIC_GUARD_BANDS=%d\n" staticPolyCnt)
        fprintf(outPort "VOIDS=%d\n" voidCnt)
        fprintf(outPort "CURVED_CAVITIES=%d\n" cavCnt)
        fprintf(outPort "OLD_LSCS_DELETED=%d\n" lscDelCnt)
        fprintf(outPort "BASE_LSCS_PLACED=%d\n" lscPlaceCnt)
        fprintf(outPort "VIAS=%d\n" viaCnt)
        fprintf(outPort "CLINES=%d\n" clineCnt)
        fprintf(outPort "ERRORS=%d\n" errCnt)

        foreach( netName auditedNets
          when( (netName && netName != "" && netName != "DUMMY")
            nObj = axlDBFindByName('net netName)
            if( nObj then
              bCnt = length(nObj->branches)
              fprintf(outPort "DB_NET_%s=BRANCHES:%d\n" netName bCnt)
            )
          )
        )
        close(outPort)
      )
      t
    )
  )
)
