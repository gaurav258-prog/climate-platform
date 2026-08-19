const pptxgen = require('pptxgenjs');
const p = new pptxgen();
p.defineLayout({ name: 'W', width: 13.33, height: 7.5 });
p.layout = 'W';

// ---------- restrained palette: green + gold + neutrals ----------
const BG='0C1411', CARD='16211C', CORE='102A1F', HAIR='27352E', HAIR2='34453C';
const INK='EDF1EC', MUTE='93A79B', FAINT='63756A';
const GREEN='79B79B', GREENB='9AD0B4', GOLD='C7A24C';
const F='Arial', SER='Cambria';

const s = p.addSlide();
s.background = { color: BG };

// ---------- helpers ----------
function T(x,y,w,h,runs,o){o=o||{};s.addText(runs,{x,y,w,h,fontFace:o.f||F,fontSize:o.s||10,bold:o.b,italic:o.i,color:o.c||INK,align:o.a||'left',valign:o.v||'top',charSpacing:o.cs,margin:0,lineSpacingMultiple:o.ls||1});}
function rr(x,y,w,h,fill,border,bw){s.addShape('roundRect',{x,y,w,h,rectRadius:0.055,fill:fill?{color:fill}:{type:'none'},line:border?{color:border,width:bw||0.75}:{type:'none'}});}
function hair(x1,y1,x2,y2,color,w,arrow){s.addShape('line',{x:Math.min(x1,x2),y:Math.min(y1,y2),w:Math.abs(x2-x1),h:Math.abs(y2-y1),flipH:x2<x1,flipV:y2<y1,line:{color:color||HAIR2,width:w||1,endArrowType:arrow?'triangle':'none'}});}
function tick(cx,cy,deg){s.addShape('triangle',{x:cx-0.075,y:cy-0.075,w:0.15,h:0.15,rotate:deg,fill:{color:GREEN},line:{type:'none'}});}

// ================= HEADER =================
T(0.55,0.42,7,0.44,'TELLUMEN',{f:SER,s:23,b:true,c:INK,cs:2});
T(0.57,0.9,9,0.24,'One truth of the Earth — and every decision that depends on it',{f:SER,s:12,i:true,c:MUTE});
T(8.0,0.5,4.78,0.3,[{text:'Functional architecture',options:{color:MUTE}},{text:'   ·   v1.49',options:{color:GREEN}}],{s:10,b:true,a:'right',cs:1});
hair(0.55,1.22,12.78,1.22,HAIR,1);

// ================= LEFT · DATA SCALE & CADENCE =================
const LX=0.55, LW=2.62;
T(LX,1.4,LW,0.2,'THE DATA WE OPERATE ON',{s:8,b:true,c:GREEN,cs:1.8});
T(LX,1.6,LW,0.18,'near-real-time · planetary scale',{s:7.4,i:true,c:MUTE});
// tone by refresh latency: bright = near-real-time, green = fast, faint = slow
// cadence colour: bright = near-real-time · green = fast · faint = slow floor
// Honest to what LANDS today (audit): flood is an ERA5-runoff proxy (GloFAS retired from CDS 2025);
// seismic is EMSC (EU) + ESHM20 zones, not global USGS/GEM; reference emissions are NACE estimates,
// not a Climate TRACE / GEM feed; Sentinel radar/optical imagery is in build, not shown as live.
const feeds=[
 ['Climate reanalysis','hourly',GREENB,0.96,'ERA5 · since 1940','Copernicus / ECMWF'],
 ['Flood (runoff proxy)','daily',GREENB,0.70,'~9 km global','ERA5-Land runoff'],
 ['Fire & thermal','≈ 3 h',GREENB,0.68,'375 m · daily','NASA FIRMS · CAMS'],
 ['Storms & cyclones','per event',GREEN,0.52,'cyclone tracks','NOAA IBTrACS'],
 ['Seismic & volcanic','continuous',GREEN,0.46,'EU seismic + zones','EMSC · GVP · ESHM20'],
 ['Deforestation','annual',FAINT,0.58,'30 m forest, 2020+','Hansen GFC'],
 ['Reference & entity','daily',FAINT,0.50,'2.7M LEIs · sector est.','GLEIF · NACE'],
 ['Your own data','on demand',FAINT,0.34,'loan-tape · SOV · EUDR','customer uploads'],
];
let fy=1.86; const rowH=0.55;
feeds.forEach(c=>{
  T(LX,fy,1.62,0.2,c[0],{s:8.8,b:true,c:INK});
  T(LX+LW-0.92,fy+0.02,0.92,0.18,c[1],{s:6.8,b:true,c:c[2],a:'right'});   // cadence, inline
  rr(LX,fy+0.235,LW,0.07,'1B2620',null,0);                               // scale-bar track
  rr(LX,fy+0.235,LW*c[3],0.07,GREEN,null,0);                             // scale-bar fill
  T(LX,fy+0.345,LW,0.16,[{text:c[4],options:{color:MUTE,italic:true}},{text:'  ·  '+c[5],options:{color:FAINT}}],{s:6.4});
  hair(LX,fy+0.5,LX+LW,fy+0.5,HAIR,0.55);
  fy+=rowH;
});
T(LX,fy+0.0,LW,0.16,'bar = relative data scale / volume',{s:6.4,i:true,c:FAINT});
// converging hairline into the loop
hair(LX+LW+0.02,3.85,3.32,3.85,GREEN,1.1,true);

// ================= CENTER · THE OPERATIONAL LOOP =================
const CX=5.75, CY=3.9, R=1.62, coreR=0.82;
// orbit ring (single hairline)
s.addShape('ellipse',{x:CX-R,y:CY-R,w:2*R,h:2*R,fill:{type:'none'},line:{color:HAIR2,width:1}});
// four small directional ticks (clockwise), muted
const dd=R*0.707;
tick(CX-dd,CY-dd,45); tick(CX+dd,CY-dd,135); tick(CX+dd,CY+dd,225); tick(CX-dd,CY+dd,315);
// core "globe"
s.addShape('ellipse',{x:CX-coreR,y:CY-coreR,w:2*coreR,h:2*coreR,fill:{color:CORE},line:{color:GREEN,width:1.5}});
s.addShape('ellipse',{x:CX-coreR*0.42,y:CY-coreR,w:2*coreR*0.42,h:2*coreR,fill:{type:'none'},line:{color:'2C5E47',width:0.75}}); // meridian
s.addShape('line',{x:CX-coreR,y:CY,w:2*coreR,h:0,line:{color:'2C5E47',width:0.75}}); // equator
T(CX-0.8,CY-0.42,1.6,0.2,'GOLDEN SOURCE',{s:8.4,b:true,c:GREENB,a:'center',cs:1});
T(CX-0.8,CY-0.16,1.6,0.36,'the one truth\nof the Earth',{s:8,i:true,c:INK,a:'center',ls:0.95});
T(CX-0.8,CY+0.3,1.6,0.18,'H3 · append-only',{s:6.6,c:FAINT,a:'center'});
// stage nodes  (01 Sense · 02 Score · 03 Project · 04 Act, clockwise from W)
const nw=1.56, nh=0.8;
function stage(cx,cy,num,name,sub){
  rr(cx-nw/2,cy-nh/2,nw,nh,CARD,HAIR,0.75);
  T(cx-nw/2+0.14,cy-nh/2+0.12,0.5,0.24,num,{f:SER,s:12,b:true,c:GREEN});
  T(cx-nw/2+0.52,cy-nh/2+0.13,nw-0.6,0.24,name,{f:SER,s:12.5,b:true,c:INK});
  T(cx-nw/2+0.14,cy+0.12,nw-0.24,0.2,sub,{s:7,i:true,c:MUTE});
}
stage(CX-R, CY,   '01','Sense',  'any address, any hazard');
stage(CX,   CY-R, '02','Score',  'per-cell hazard · € at risk');
stage(CX+R, CY,   '03','Project','parametric + CMIP6');
stage(CX,   CY+R, '04','Act',    'alert · adapt · file');
T(CX-2.1,CY+R+0.55,4.2,0.18,'Any-Address engine · Calibration & Grades A–E · Projections · Reference Resolver',{s:6.9,i:true,c:FAINT,a:'center'});

// ================= HONESTY GATE (single gold accent) =================
const GX=8.95, GY=CY, gR=0.56;
hair(CX+R+0.8,CY,GX-gR,GY,GOLD,1.2,true);
s.addShape('ellipse',{x:GX-gR,y:GY-gR,w:2*gR,h:2*gR,fill:{color:'241E10'},line:{color:GOLD,width:1.5}});
T(GX-gR,GY-0.34,2*gR,0.16,'HONESTY GATE',{s:7,b:true,c:GOLD,a:'center',cs:0.5});
T(GX-gR,GY-0.14,2*gR,0.22,'r² ≥ 0.40',{f:SER,s:12,b:true,c:INK,a:'center'});
T(GX-gR,GY+0.16,2*gR,0.18,'our publish standard',{s:6.4,i:true,c:FAINT,a:'center'});

// ================= RIGHT · TWO SIDES OF ONE TRUTH =================
const RX=9.62, RW=3.16;
function listRow(y,title,sub,tc){
  T(RX,y,1.55,0.22,title,{s:9.2,b:true,c:tc||INK,v:'middle'});
  T(RX+1.45,y,RW-1.45,0.22,sub,{s:7.4,i:true,c:MUTE,a:'right',v:'middle'});
  hair(RX,y+0.31,RX+RW,y+0.31,HAIR,0.75);
}
// gate → two sides (equal-length, symmetric about the gate)
hair(GX+gR-0.06,GY-0.32,RX-0.12,2.0,GREEN,1,true);
hair(GX+gR-0.06,GY+0.32,RX-0.12,5.8,GOLD,1,true);

T(RX,1.5,RW,0.2,'OPERATE — RUN THE BUSINESS',{s:8,b:true,c:GREEN,cs:1.5});
const oper=[['Agriculture','flagship · supply-chain € at risk'],['Banking','financed physical risk'],['Insurance','SOV · claims exposure'],['Asset management','SFDR PAI · Taxonomy'],['Real estate','asset-level hazard']];
let oy=1.84; oper.forEach(r=>{ listRow(oy,r[0],r[1]); oy+=0.4; });

T(RX,3.92,RW,0.2,'COMPLY — SATISFY THE LAW',{s:8,b:true,c:GOLD,cs:1.5});
const comp=[['CSRD · ESRS','E1 · E3 · E4 physical'],['EU Taxonomy','Art. 8 adaptation'],['EUDR','per-plot DDS → TRACES'],['SFDR · PAI','financial verticals'],['iXBRL · Assurance','ESEF filing · evidence pack']];
let cy2=4.26; comp.forEach(r=>{ listRow(cy2,r[0],r[1]); cy2+=0.4; });
T(RX,6.34,RW,0.2,[{text:'→ the regulator verifies the same truth',options:{color:INK,italic:true}},{text:'  · next',options:{color:GOLD,bold:true}}],{s:7.6});

// ================= GOVERNANCE + FOOTER =================
hair(0.55,6.66,12.78,6.66,HAIR,1);
T(0.55,6.78,12.23,0.2,[{text:'GOVERNED END-TO-END   ',options:{color:GREEN,bold:true}},
 {text:'role-based access · four-eyes approvals · immutable report snapshots · full audit trail · configurable reporting basis',options:{color:MUTE}}],
 {s:8,a:'left',cs:0.5});
T(0.55,7.12,6,0.2,'TELLUMEN',{s:7.5,b:true,c:FAINT,cs:2});
T(8.0,7.12,4.78,0.2,'CONFIDENTIAL',{s:7.5,b:true,c:FAINT,a:'right',cs:2});

p.writeFile({ fileName: '/Users/gauravsachdeva/Downloads/Tellumen-Functional-Architecture.pptx' }).then(f=>console.log('wrote',f));
