
module s1423 ( CK, G0, G1, G10, G11, G12, G13, G14, G15, G16, G2, G3, G4, G5, 
        G6, G7, G701BF, G702, G726, G727, G729, G8, G9, test_se, test_si, 
        test_so );
  input CK, G0, G1, G10, G11, G12, G13, G14, G15, G16, G2, G3, G4, G5, G6, G7,
         G8, G9, test_se, test_si;
  output G701BF, G702, G726, G727, G729, test_so;
  wire   G729, n378, G713, G707, n360, G705, n345, n363, G693, G657, G687,
         G682, G675, G669, G663, G613, G608, G590, G577, G573, G569, G565,
         G548, G541, n369, G536, G531, n356, G526, n346, n364, G503, n350,
         G498, G494, G477, n372, G469, n351, G464, n358, G459, n352, G451,
         G447, G441, G438, G427, G424, G416, G408, n361, G405, G397, G392,
         G384, G379, G373, G365, n373, G360, n366, G321, G315, G309, G303,
         G260, G252, n354, G247, G242, n353, G237, G328BF, G23, G332BF, G22,
         G218, G214, G208, G198, G193, n374, G189, G175, G166, n359, n367,
         G159, G154, n375, G149, G144, n376, G140, G129, G125, n368, G118,
         G113, n377, G109, n357, n370, n371, n75, n76, n77, n78, n79, n80, n81,
         n82, n83, n84, n85, n86, n87, n88, n89, n90, n91, n92, n93, n94, n95,
         n96, n97, n98, n99, n100, n101, n102, n103, n104, n105, n106, n107,
         n108, n109, n110, n111, n112, n113, n114, n115, n116, n117, n118,
         n119, n120, n121, n122, n123, n124, n125, n126, n127, n128, n129,
         n130, n131, n132, n133, n134, n135, n136, n137, n138, n139, n141,
         n142, n143, n144, n145, n146, n147, n148, n149, n150, n151, n152,
         n153, n154, n155, n156, n157, n158, n159, n160, n161, n162, n163,
         n164, n165, n166, n167, n168, n169, n170, n171, n172, n173, n174,
         n175, n176, n177, n178, n179, n180, n181, n182, n183, n184, n185,
         n186, n187, n188, n189, n190, n191, n192, n193, n194, n195, n196,
         n197, n198, n199, n200, n201, n202, n203, n204, n205, n206, n207,
         n208, n209, n210, n211, n212, n213, n214, n215, n216, n217, n218,
         n219, n220, n221, n222, n223, n224, n225, n226, n227, n228, n229,
         n230, n231, n232, n233, n234, n235, n236, n237, n238, n239, n240,
         n241, n242, n243, n244, n245, n246, n247, n248, n249, n250, n251,
         n252, n253, n254, n255, n256, n257, n258, n259, n260, n261, n262,
         n263, n264, n265, n266, n267, n268, n269, n270, n271, n272, n273,
         n274, n275, n276, n277, n278, n279, n280, n281, n282, n283, n284,
         n285, n286, n287, n288, n289, n290, n291, n292, n293, n294, n295,
         n296, n297, n298, n299, n300, n301, n302, n303, n304, n305, n306,
         n307, n308, n309, n310, n311, n312, n313, n314, n315, n316, n317,
         n318, n319, n320, n321, n322, n323, n324, n325, n326, n327, n328,
         n329, n330, n331, n332, n333, n334, n335, n336, n337, n338, n339,
         n340, n341, n342, n343, n344, n347, n348, n349, n355, n362, n365,
         n379, n380, n381, n382, n383, n384, n385, n386, n387, n388, n389,
         n390, n391, n392, n393, n394, n395, n396, n397, n398, n399, n400,
         n401, n402, n403, n404, n405, n406, n407, n408, n409, n410, n411,
         n412, n413, n414, n415, n416, n417, n418, n419, n420, n421, n422,
         n423, n424, n425, n426, n427, n428, n429, n430, n431, n432, n433,
         n434, n435, n436, n437, n438, n439, n440, n441, n442, n443, n444,
         n445, n446, n447, n448, n449, n450, n451, n452, n453, n454, n455,
         n456, n457, n458, n459, n460, n461, n462, n463, n464, n465, n466,
         n467, n468, n469, n470, n471, n472, n473, n476, n477, n478, n479,
         n480, n481, n482, n483, n484, n485, n486, n487, n488, n489, n490,
         n491, n492, n493, n494, n495, n496, n497, n498, n499, n500, n501,
         n502, n503, n504, n505, n506, n507, n508, n509, n510, n511, n512,
         n513, n514, n515, n516, n517, n518, n519, n520, n521, n522, n523,
         n524, n525, n526, n527, n528, n529, n530, n531, n532, n533, n534,
         n535, n536, n537, n538, n539;

wire Trojan_out0,  troj19_0N87,  troj19_0N88,  troj19_0N89,  troj19_0N90,  troj19_0N91,  troj19_0N92,  troj19_0N93,  troj19_0n1,  troj19_0n2,  troj19_0n3,  troj19_0n4,  troj19_0n5,  troj19_0n6,  troj19_0n7,  troj19_0n8,  troj19_0n9,  troj19_0n10,  troj19_0n11,  troj19_0n12,  troj19_0n13,  troj19_0n14,  troj19_0n15,  troj19_0n16,  troj19_0n17,  troj19_0n18,  troj19_0n19,  troj19_0n20,  troj19_0n21,  troj19_0n22,  troj19_0n23,  Trigger_en0_0,  trig47_0n1,  trig47_0n2,  trig47_0n3,  trig47_0n4,  trig47_0n5,  trig47_0n6,  tempn224,  Trigger_en1_19,  troj19_1n1,  troj19_1n2,  troj19_1n3,  troj19_1n4,  tempn84;

  assign test_so = G729;

  nor2s3 U1 ( .DIN1(n111), .DIN2(n99), .Q(G727) );
  nor5s3 U2 ( .DIN1(n139), .DIN2(n143), .DIN3(n95), .DIN4(n345), .DIN5(n96), 
        .Q(G713) );
  nnd2s3 U3 ( .DIN1(n146), .DIN2(n147), .Q(G707) );
  nnd2s3 U4 ( .DIN1(n148), .DIN2(n75), .Q(n147) );
  nnd2s3 U5 ( .DIN1(n360), .DIN2(n149), .Q(n146) );
  and2s3 U6 ( .DIN1(G14), .DIN2(n150), .Q(G705) );
  nnd3s3 U7 ( .DIN1(n151), .DIN2(n152), .DIN3(n153), .Q(n150) );
  nnd2s3 U8 ( .DIN1(n378), .DIN2(n154), .Q(n153) );
  nnd2s3 U9 ( .DIN1(n155), .DIN2(n156), .Q(n154) );
  nnd3s3 U10 ( .DIN1(n157), .DIN2(n142), .DIN3(n158), .Q(n156) );
  nnd2s3 U11 ( .DIN1(n76), .DIN2(n159), .Q(n158) );
  nnd2s3 U12 ( .DIN1(n160), .DIN2(n141), .Q(n159) );
  nnd2s3 U13 ( .DIN1(G6), .DIN2(n133), .Q(n155) );
  nnd3s3 U14 ( .DIN1(n161), .DIN2(n157), .DIN3(n98), .Q(n152) );
  nnd2s3 U15 ( .DIN1(n76), .DIN2(n162), .Q(n161) );
  nnd3s3 U16 ( .DIN1(n105), .DIN2(n160), .DIN3(n345), .Q(n162) );
  or5s3 U17 ( .DIN1(n93), .DIN2(n163), .DIN3(n164), .DIN4(n165), .DIN5(n166), 
        .Q(n160) );
  and2s3 U18 ( .DIN1(n167), .DIN2(n354), .Q(n164) );
  nnd3s3 U19 ( .DIN1(n169), .DIN2(n99), .DIN3(n170), .Q(n151) );
  nnd2s3 U20 ( .DIN1(n171), .DIN2(n172), .Q(n170) );
  or2s3 U21 ( .DIN1(n89), .DIN2(n361), .Q(n172) );
  nnd2s3 U22 ( .DIN1(n436), .DIN2(n89), .Q(n171) );
  and4s2 U23 ( .DIN1(n173), .DIN2(n174), .DIN3(n175), .DIN4(n176), .Q(G702) );
  nor2s3 U24 ( .DIN1(n177), .DIN2(n99), .Q(n176) );
  nor2s3 U25 ( .DIN1(n360), .DIN2(n178), .Q(n177) );
  nnd2s3 U26 ( .DIN1(n179), .DIN2(n102), .Q(n175) );
  nnd3s3 U27 ( .DIN1(n180), .DIN2(n135), .DIN3(n363), .Q(n174) );
  nnd3s3 U28 ( .DIN1(n129), .DIN2(n101), .DIN3(n181), .Q(n173) );
  nnd3s3 U29 ( .DIN1(n182), .DIN2(n183), .DIN3(G657), .Q(G693) );
  nnd3s3 U30 ( .DIN1(n88), .DIN2(n104), .DIN3(n138), .Q(n183) );
  nnd2s3 U31 ( .DIN1(n184), .DIN2(n89), .Q(n182) );
  nnd3s3 U32 ( .DIN1(n185), .DIN2(n186), .DIN3(G657), .Q(G687) );
  nnd3s3 U33 ( .DIN1(n89), .DIN2(n104), .DIN3(n138), .Q(n186) );
  nnd2s3 U34 ( .DIN1(n184), .DIN2(n99), .Q(n185) );
  nnd3s3 U35 ( .DIN1(n187), .DIN2(n103), .DIN3(G657), .Q(G682) );
  nor2s3 U36 ( .DIN1(n138), .DIN2(n432), .Q(n184) );
  nnd2s3 U37 ( .DIN1(n99), .DIN2(n104), .Q(n187) );
  nnd2s3 U38 ( .DIN1(n188), .DIN2(n189), .Q(G675) );
  nnd2s3 U39 ( .DIN1(n148), .DIN2(n100), .Q(n189) );
  nnd2s3 U40 ( .DIN1(n149), .DIN2(n101), .Q(n188) );
  nnd2s3 U41 ( .DIN1(n190), .DIN2(n191), .Q(G669) );
  nnd2s3 U42 ( .DIN1(n148), .DIN2(n101), .Q(n191) );
  nnd2s3 U43 ( .DIN1(n149), .DIN2(n102), .Q(n190) );
  nnd2s3 U44 ( .DIN1(n192), .DIN2(n193), .Q(G663) );
  nnd2s3 U45 ( .DIN1(n148), .DIN2(n102), .Q(n193) );
  nor2s3 U46 ( .DIN1(n139), .DIN2(G11), .Q(n148) );
  nnd2s3 U47 ( .DIN1(n363), .DIN2(n149), .Q(n192) );
  and2s3 U48 ( .DIN1(G11), .DIN2(G14), .Q(n149) );
  and2s3 U49 ( .DIN1(G13), .DIN2(G14), .Q(G657) );
  nnd2s3 U50 ( .DIN1(n194), .DIN2(n195), .Q(G613) );
  or2s3 U51 ( .DIN1(n196), .DIN2(n370), .Q(n195) );
  nnd2s3 U52 ( .DIN1(G11), .DIN2(n196), .Q(n194) );
  nnd2s3 U53 ( .DIN1(n197), .DIN2(n198), .Q(G608) );
  or2s3 U54 ( .DIN1(n196), .DIN2(n371), .Q(n198) );
  nnd2s3 U55 ( .DIN1(G10), .DIN2(n196), .Q(n197) );
  nor2s3 U56 ( .DIN1(n199), .DIN2(n200), .Q(G590) );
  nor2s3 U57 ( .DIN1(n201), .DIN2(n81), .Q(n199) );
  nor2s3 U58 ( .DIN1(n345), .DIN2(n202), .Q(n201) );
  nor2s3 U59 ( .DIN1(n76), .DIN2(n203), .Q(n202) );
  nnd2s3 U60 ( .DIN1(n204), .DIN2(n205), .Q(G577) );
  or2s3 U61 ( .DIN1(n196), .DIN2(n444), .Q(n205) );
  nnd2s3 U62 ( .DIN1(G9), .DIN2(n196), .Q(n204) );
  nnd2s3 U63 ( .DIN1(n206), .DIN2(n207), .Q(G573) );
  or2s3 U64 ( .DIN1(n196), .DIN2(n445), .Q(n207) );
  nnd2s3 U65 ( .DIN1(G8), .DIN2(n196), .Q(n206) );
  nnd2s3 U66 ( .DIN1(n208), .DIN2(n209), .Q(G569) );
  or2s3 U67 ( .DIN1(n196), .DIN2(n446), .Q(n209) );
  nnd2s3 U68 ( .DIN1(G7), .DIN2(n196), .Q(n208) );
  nnd2s3 U69 ( .DIN1(n210), .DIN2(n211), .Q(G565) );
  or2s3 U70 ( .DIN1(n196), .DIN2(n447), .Q(n211) );
  nnd2s3 U71 ( .DIN1(G6), .DIN2(n196), .Q(n210) );
  nnd2s3 U72 ( .DIN1(G14), .DIN2(n212), .Q(n196) );
  nnd2s3 U73 ( .DIN1(n213), .DIN2(n89), .Q(n212) );
  nor2s3 U74 ( .DIN1(n200), .DIN2(n214), .Q(G548) );
  xnr2s3 U75 ( .DIN1(n472), .DIN2(n215), .Q(n214) );
  and3s3 U76 ( .DIN1(n216), .DIN2(n215), .DIN3(n90), .Q(G541) );
  nnd3s3 U77 ( .DIN1(n107), .DIN2(n108), .DIN3(n80), .Q(n215) );
  nnd2s3 U78 ( .DIN1(n369), .DIN2(n217), .Q(n216) );
  nnd2s3 U79 ( .DIN1(n80), .DIN2(n108), .Q(n217) );
  nor2s3 U80 ( .DIN1(n200), .DIN2(n219), .Q(G536) );
  xnr2s3 U81 ( .DIN1(n471), .DIN2(n218), .Q(n219) );
  and3s3 U82 ( .DIN1(n220), .DIN2(n218), .DIN3(n90), .Q(G531) );
  nnd3s3 U83 ( .DIN1(n110), .DIN2(n109), .DIN3(n81), .Q(n218) );
  nnd2s3 U84 ( .DIN1(n356), .DIN2(n221), .Q(n220) );
  nnd2s3 U85 ( .DIN1(n81), .DIN2(n110), .Q(n221) );
  nor2s3 U86 ( .DIN1(n200), .DIN2(n223), .Q(G526) );
  xnr2s3 U87 ( .DIN1(n346), .DIN2(n222), .Q(n223) );
  nnd3s3 U88 ( .DIN1(n224), .DIN2(n203), .DIN3(n225), .Q(n222) );
  nnd3s3 U89 ( .DIN1(n169), .DIN2(n88), .DIN3(n226), .Q(n225) );
  nnd2s3 U90 ( .DIN1(n227), .DIN2(n134), .Q(n226) );
  nnd2s3 U91 ( .DIN1(n98), .DIN2(n228), .Q( tempn224 ) );
  nnd2s3 U92 ( .DIN1(n82), .DIN2(n364), .Q(n228) );
  nnd2s3 U93 ( .DIN1(n230), .DIN2(n231), .Q(n200) );
  nnd2s3 U94 ( .DIN1(G9), .DIN2(n378), .Q(n231) );
  nnd3s3 U95 ( .DIN1(n232), .DIN2(n233), .DIN3(n234), .Q(G503) );
  or2s3 U96 ( .DIN1(n235), .DIN2(n452), .Q(n234) );
  nnd2s3 U97 ( .DIN1(G5), .DIN2(n236), .Q(n233) );
  nnd2s3 U98 ( .DIN1(G2), .DIN2(n237), .Q(n232) );
  nnd3s3 U99 ( .DIN1(n238), .DIN2(n239), .DIN3(n240), .Q(G498) );
  or2s3 U100 ( .DIN1(n235), .DIN2(n451), .Q(n240) );
  nnd2s3 U101 ( .DIN1(G4), .DIN2(n236), .Q(n239) );
  nnd2s3 U102 ( .DIN1(G1), .DIN2(n237), .Q(n238) );
  nnd3s3 U103 ( .DIN1(n241), .DIN2(n242), .DIN3(n243), .Q(G494) );
  or2s3 U104 ( .DIN1(n235), .DIN2(n450), .Q(n243) );
  nnd2s3 U105 ( .DIN1(G3), .DIN2(n236), .Q(n242) );
  nor2s3 U106 ( .DIN1(n97), .DIN2(n350), .Q(n236) );
  nnd2s3 U107 ( .DIN1(G0), .DIN2(n237), .Q(n241) );
  nor2s3 U108 ( .DIN1(n117), .DIN2(n97), .Q(n237) );
  nnd2s3 U109 ( .DIN1(G14), .DIN2(n230), .Q(n235) );
  and3s3 U110 ( .DIN1(n244), .DIN2(n245), .DIN3(n111), .Q(G477) );
  nnd2s3 U111 ( .DIN1(n372), .DIN2(n246), .Q(n245) );
  or2s3 U112 ( .DIN1(n247), .DIN2(n351), .Q(n246) );
  or3s3 U113 ( .DIN1(n351), .DIN2(n372), .DIN3(n247), .Q(n244) );
  nor2s3 U114 ( .DIN1(n213), .DIN2(n248), .Q(G469) );
  xnr2s3 U115 ( .DIN1(n351), .DIN2(n247), .Q(n248) );
  and3s3 U116 ( .DIN1(n249), .DIN2(n247), .DIN3(n111), .Q(G464) );
  nnd3s3 U117 ( .DIN1(n114), .DIN2(n113), .DIN3(n250), .Q(n247) );
  nnd2s3 U118 ( .DIN1(n358), .DIN2(n251), .Q(n249) );
  nnd2s3 U119 ( .DIN1(n250), .DIN2(n114), .Q(n251) );
  nor2s3 U120 ( .DIN1(n252), .DIN2(n213), .Q(G459) );
  xnr2s3 U121 ( .DIN1(n250), .DIN2(n114), .Q(n252) );
  nnd2s3 U122 ( .DIN1(n99), .DIN2(n253), .Q(n250) );
  nnd2s3 U123 ( .DIN1(n254), .DIN2(n255), .Q(n253) );
  nnd2s3 U124 ( .DIN1(n89), .DIN2(n178), .Q(n255) );
  nnd2s3 U125 ( .DIN1(n256), .DIN2(n257), .Q(G451) );
  nnd2s3 U126 ( .DIN1(n258), .DIN2(n115), .Q(n257) );
  or2s3 U127 ( .DIN1(n213), .DIN2(n366), .Q(n256) );
  nnd2s3 U128 ( .DIN1(n112), .DIN2(n259), .Q(G447) );
  nnd2s3 U129 ( .DIN1(G14), .DIN2(n115), .Q(n259) );
  nnd2s3 U130 ( .DIN1(n260), .DIN2(n261), .Q(G441) );
  nnd2s3 U131 ( .DIN1(n258), .DIN2(n117), .Q(n261) );
  nor2s3 U132 ( .DIN1(n262), .DIN2(n139), .Q(n258) );
  nnd2s3 U133 ( .DIN1(n111), .DIN2(n116), .Q(n260) );
  nor2s3 U134 ( .DIN1(n263), .DIN2(n139), .Q(G438) );
  nor2s3 U135 ( .DIN1(n76), .DIN2(n117), .Q(n263) );
  nnd2s3 U136 ( .DIN1(n264), .DIN2(n265), .Q(n143) );
  nnd2s3 U137 ( .DIN1(n266), .DIN2(n169), .Q(n265) );
  nnd2s3 U138 ( .DIN1(n267), .DIN2(n268), .Q(n266) );
  nnd2s3 U139 ( .DIN1(n134), .DIN2(n88), .Q(n268) );
  nnd2s3 U140 ( .DIN1(n462), .DIN2(n465), .Q(n267) );
  nnd2s3 U141 ( .DIN1(n364), .DIN2(n98), .Q(n264) );
  and3s3 U142 ( .DIN1(n269), .DIN2(n178), .DIN3(G14), .Q(G427) );
  nnd3s3 U143 ( .DIN1(n436), .DIN2(n119), .DIN3(n270), .Q(n178) );
  nnd2s3 U144 ( .DIN1(n118), .DIN2(n271), .Q(n269) );
  nor2s3 U145 ( .DIN1(n272), .DIN2(n273), .Q(G424) );
  nor2s3 U146 ( .DIN1(n274), .DIN2(n119), .Q(n272) );
  nor2s3 U147 ( .DIN1(n438), .DIN2(n78), .Q(n274) );
  nor2s3 U148 ( .DIN1(n273), .DIN2(n275), .Q(G416) );
  xnr2s3 U149 ( .DIN1(n438), .DIN2(n78), .Q(n275) );
  nnd2s3 U150 ( .DIN1(G14), .DIN2(n271), .Q(n273) );
  nnd2s3 U151 ( .DIN1(n270), .DIN2(n119), .Q(n271) );
  and3s3 U152 ( .DIN1(n276), .DIN2(n79), .DIN3(G14), .Q(G408) );
  nnd2s3 U153 ( .DIN1(n361), .DIN2(n277), .Q(n276) );
  nor2s3 U154 ( .DIN1(n278), .DIN2(n279), .Q(G405) );
  nor2s3 U155 ( .DIN1(n280), .DIN2(n120), .Q(n278) );
  nor2s3 U156 ( .DIN1(n439), .DIN2(n281), .Q(n280) );
  nor2s3 U157 ( .DIN1(n282), .DIN2(n279), .Q(G397) );
  nnd2s3 U158 ( .DIN1(G14), .DIN2(n277), .Q(n279) );
  xnr2s3 U159 ( .DIN1(n281), .DIN2(n439), .Q(n282) );
  nor2s3 U160 ( .DIN1(n283), .DIN2(n284), .Q(G392) );
  nor2s3 U161 ( .DIN1(n285), .DIN2(n121), .Q(n283) );
  and3s3 U162 ( .DIN1(n286), .DIN2(n85), .DIN3(n84), .Q(G384) );
  nor2s3 U163 ( .DIN1(n86), .DIN2(n440), .Q(n285) );
  nnd2s3 U164 ( .DIN1(n440), .DIN2(n86), .Q(n286) );
  and3s3 U165 ( .DIN1(n287), .DIN2(n86), .DIN3(n84), .Q(G379) );
  nnd2s3 U166 ( .DIN1(G14), .DIN2(n288), .Q(n284) );
  nnd2s3 U167 ( .DIN1(n449), .DIN2(n290), .Q(n287) );
  nor2s3 U168 ( .DIN1(n291), .DIN2(n77), .Q(G373) );
  and2s3 U169 ( .DIN1(n292), .DIN2(n442), .Q(n291) );
  and3s3 U170 ( .DIN1(n293), .DIN2(n292), .DIN3(n294), .Q(G365) );
  or3s3 U171 ( .DIN1(n373), .DIN2(n441), .DIN3(n295), .Q(n292) );
  nnd2s3 U172 ( .DIN1(n373), .DIN2(n296), .Q(n293) );
  or2s3 U173 ( .DIN1(n295), .DIN2(n441), .Q(n296) );
  nor2s3 U174 ( .DIN1(n297), .DIN2(n77), .Q(G360) );
  nor2s3 U175 ( .DIN1(n139), .DIN2(n270), .Q(n294) );
  nor2s3 U176 ( .DIN1(n442), .DIN2(n295), .Q(n270) );
  xnr2s3 U177 ( .DIN1(n441), .DIN2(n295), .Q(n297) );
  nor2s3 U178 ( .DIN1(n458), .DIN2(n254), .Q(n295) );
  nor2s3 U179 ( .DIN1(n277), .DIN2(n361), .Q(n254) );
  or2s3 U180 ( .DIN1(n281), .DIN2(n443), .Q(n277) );
  and2s3 U181 ( .DIN1(n298), .DIN2(n299), .Q(n281) );
  or3s3 U182 ( .DIN1(n169), .DIN2(n364), .DIN3(n229), .Q(n299) );
  nnd2s3 U183 ( .DIN1(n83), .DIN2(n169), .Q(n298) );
  nnd2s3 U184 ( .DIN1(n99), .DIN2(n300), .Q(n169) );
  nnd4s2 U185 ( .DIN1(n366), .DIN2(n345), .DIN3(G16), .DIN4(n105), .Q(n300) );
  or5s3 U186 ( .DIN1(n301), .DIN2(n302), .DIN3(n303), .DIN4(n304), .DIN5(n305), 
        .Q(n203) );
  xnr2s3 U187 ( .DIN1(n445), .DIN2(n108), .Q(n305) );
  xnr2s3 U188 ( .DIN1(n444), .DIN2(n107), .Q(n304) );
  xnr2s3 U189 ( .DIN1(n447), .DIN2(n110), .Q(n303) );
  xnr2s3 U190 ( .DIN1(n446), .DIN2(n109), .Q(n302) );
  xnr2s3 U191 ( .DIN1(n306), .DIN2(n106), .Q(n301) );
  nnd4s2 U192 ( .DIN1(n444), .DIN2(n445), .DIN3(n447), .DIN4(n446), .Q(n306)
         );
  nnd2s3 U193 ( .DIN1(n307), .DIN2(n308), .Q(G321) );
  nnd2s3 U194 ( .DIN1(n309), .DIN2(n122), .Q(n308) );
  nnd2s3 U195 ( .DIN1(n310), .DIN2(n123), .Q(n307) );
  nnd2s3 U196 ( .DIN1(n311), .DIN2(n312), .Q(G315) );
  nnd2s3 U197 ( .DIN1(n309), .DIN2(n123), .Q(n312) );
  nnd2s3 U198 ( .DIN1(n310), .DIN2(n124), .Q(n311) );
  nnd2s3 U199 ( .DIN1(n313), .DIN2(n314), .Q(G309) );
  nnd2s3 U200 ( .DIN1(n309), .DIN2(n124), .Q(n314) );
  nnd2s3 U201 ( .DIN1(n310), .DIN2(n125), .Q(n313) );
  nnd2s3 U202 ( .DIN1(n315), .DIN2(n316), .Q(G303) );
  nnd2s3 U203 ( .DIN1(n309), .DIN2(n125), .Q(n316) );
  nor2s3 U204 ( .DIN1(n317), .DIN2(n139), .Q(n309) );
  nnd2s3 U205 ( .DIN1(G12), .DIN2(n310), .Q(n315) );
  and2s3 U206 ( .DIN1(G14), .DIN2(n317), .Q(n310) );
  nnd2s3 U207 ( .DIN1(n89), .DIN2(n288), .Q(n317) );
  nnd2s3 U208 ( .DIN1(n289), .DIN2(n121), .Q(n288) );
  nor2s3 U209 ( .DIN1(n290), .DIN2(n449), .Q(n289) );
  nor2s3 U210 ( .DIN1(n318), .DIN2(n319), .Q(G260) );
  xnr2s3 U211 ( .DIN1(n357), .DIN2(n320), .Q(n319) );
  and3s3 U212 ( .DIN1(n321), .DIN2(n320), .DIN3(n91), .Q(G252) );
  or3s3 U213 ( .DIN1(n354), .DIN2(n470), .DIN3(n322), .Q(n320) );
  nnd2s3 U214 ( .DIN1(n354), .DIN2(n323), .Q(n321) );
  or2s3 U215 ( .DIN1(n322), .DIN2(n470), .Q(n323) );
  nor2s3 U216 ( .DIN1(n318), .DIN2(n324), .Q(G247) );
  xnr2s3 U217 ( .DIN1(n470), .DIN2(n322), .Q(n324) );
  and3s3 U218 ( .DIN1(n325), .DIN2(n322), .DIN3(n91), .Q(G242) );
  nnd3s3 U219 ( .DIN1(n127), .DIN2(n128), .DIN3(n326), .Q(n322) );
  nnd2s3 U220 ( .DIN1(n353), .DIN2(n327), .Q(n325) );
  nnd2s3 U221 ( .DIN1(n326), .DIN2(n128), .Q(n327) );
  nor2s3 U222 ( .DIN1(n318), .DIN2(n328), .Q(G237) );
  xnr2s3 U223 ( .DIN1(n128), .DIN2(n326), .Q(n328) );
  nor2s3 U224 ( .DIN1(n329), .DIN2(G328BF), .Q(n326) );
  nnd2s3 U225 ( .DIN1(n330), .DIN2(n331), .Q(G328BF) );
  nnd2s3 U226 ( .DIN1(G332BF), .DIN2(G15), .Q(n331) );
  nnd2s3 U227 ( .DIN1(n332), .DIN2(n333), .Q(G332BF) );
  or2s3 U228 ( .DIN1(n329), .DIN2(G15), .Q(n333) );
  nnd2s3 U229 ( .DIN1(n334), .DIN2(G22), .Q(n332) );
  or5s3 U230 ( .DIN1(G15), .DIN2(n122), .DIN3(n123), .DIN4(n124), .DIN5(n125), 
        .Q(n334) );
  nnd2s3 U231 ( .DIN1(G701BF), .DIN2(G23), .Q(n330) );
  nnd4s2 U232 ( .DIN1(n122), .DIN2(n123), .DIN3(n124), .DIN4(n125), .Q(n329)
         );
  nnd2s3 U233 ( .DIN1(n230), .DIN2(n335), .Q(n318) );
  nnd2s3 U234 ( .DIN1(G7), .DIN2(n378), .Q(n335) );
  nnd2s3 U235 ( .DIN1(n213), .DIN2(n99), .Q(n230) );
  nnd2s3 U236 ( .DIN1(G14), .DIN2(n262), .Q(n213) );
  nnd4s2 U237 ( .DIN1(n336), .DIN2(n337), .DIN3(n338), .DIN4(n339), .Q(n262)
         );
  xnr2s3 U238 ( .DIN1(n372), .DIN2(n340), .Q(n339) );
  nnd3s3 U239 ( .DIN1(n451), .DIN2(n452), .DIN3(n450), .Q(n340) );
  xnr2s3 U240 ( .DIN1(n452), .DIN2(n351), .Q(n338) );
  xnr2s3 U241 ( .DIN1(n450), .DIN2(n352), .Q(n337) );
  xnr2s3 U242 ( .DIN1(n358), .DIN2(n451), .Q(n336) );
  nor2s3 U243 ( .DIN1(n139), .DIN2(n341), .Q(G218) );
  xnr2s3 U244 ( .DIN1(n129), .DIN2(n181), .Q(n341) );
  nor2s3 U245 ( .DIN1(n342), .DIN2(n139), .Q(G214) );
  nor2s3 U246 ( .DIN1(n343), .DIN2(n181), .Q(n342) );
  nor2s3 U247 ( .DIN1(n344), .DIN2(n130), .Q(n343) );
  nor2s3 U248 ( .DIN1(n347), .DIN2(n139), .Q(G208) );
  xnr2s3 U249 ( .DIN1(n290), .DIN2(n461), .Q(n347) );
  nor2s3 U250 ( .DIN1(n139), .DIN2(n348), .Q(G198) );
  xnr2s3 U251 ( .DIN1(n364), .DIN2(n229), .Q(n348) );
  and3s3 U252 ( .DIN1(n349), .DIN2(n229), .DIN3(G14), .Q(G193) );
  nnd3s3 U253 ( .DIN1(n131), .DIN2(n132), .DIN3(n355), .Q(n229) );
  nnd2s3 U254 ( .DIN1(n374), .DIN2(n362), .Q(n349) );
  nnd2s3 U255 ( .DIN1(n355), .DIN2(n132), .Q(n362) );
  nor2s3 U256 ( .DIN1(n139), .DIN2(n365), .Q(G189) );
  xnr2s3 U257 ( .DIN1(n457), .DIN2(n355), .Q(n365) );
  nnd2s3 U258 ( .DIN1(n89), .DIN2(n379), .Q(n355) );
  nnd2s3 U259 ( .DIN1(n181), .DIN2(n129), .Q(n379) );
  and2s3 U260 ( .DIN1(n344), .DIN2(n130), .Q(n181) );
  and2s3 U261 ( .DIN1(n461), .DIN2(n83), .Q(n344) );
  nor2s3 U262 ( .DIN1(n465), .DIN2(n179), .Q(n290) );
  nor2s3 U263 ( .DIN1(n139), .DIN2(n133), .Q(G175) );
  nor2s3 U264 ( .DIN1(n380), .DIN2(n139), .Q(G166) );
  nor2s3 U265 ( .DIN1(n381), .DIN2(n179), .Q(n380) );
  nor2s3 U266 ( .DIN1(n134), .DIN2(n87), .Q(n179) );
  nor2s3 U267 ( .DIN1(n359), .DIN2(n227), .Q(n381) );
  and3s3 U268 ( .DIN1(n382), .DIN2(n87), .DIN3(G14), .Q(G159) );
  nor2s3 U269 ( .DIN1(n383), .DIN2(n367), .Q(n227) );
  nnd2s3 U270 ( .DIN1(n367), .DIN2(n383), .Q(n382) );
  and3s3 U271 ( .DIN1(n384), .DIN2(n383), .DIN3(G14), .Q(G154) );
  or3s3 U272 ( .DIN1(n375), .DIN2(n463), .DIN3(n385), .Q(n383) );
  nnd2s3 U273 ( .DIN1(n375), .DIN2(n386), .Q(n384) );
  or2s3 U274 ( .DIN1(n385), .DIN2(n463), .Q(n386) );
  nor2s3 U275 ( .DIN1(n139), .DIN2(n387), .Q(G149) );
  xnr2s3 U276 ( .DIN1(n463), .DIN2(n385), .Q(n387) );
  and3s3 U277 ( .DIN1(n388), .DIN2(n385), .DIN3(G14), .Q(G144) );
  or3s3 U278 ( .DIN1(n376), .DIN2(n464), .DIN3(n389), .Q(n385) );
  nnd2s3 U279 ( .DIN1(n376), .DIN2(n390), .Q(n388) );
  or2s3 U280 ( .DIN1(n389), .DIN2(n464), .Q(n390) );
  nor2s3 U281 ( .DIN1(n139), .DIN2(n391), .Q(G140) );
  xor2s3 U282 ( .DIN1(n464), .DIN2(n389), .Q(n391) );
  and2s3 U283 ( .DIN1(n88), .DIN2(n392), .Q(n389) );
  nnd2s3 U284 ( .DIN1(n180), .DIN2(n135), .Q(n392) );
  nor2s3 U285 ( .DIN1(n139), .DIN2(n393), .Q(G129) );
  xnr2s3 U286 ( .DIN1(n135), .DIN2(n180), .Q(n393) );
  nor2s3 U287 ( .DIN1(n394), .DIN2(n139), .Q(G125) );
  nor2s3 U288 ( .DIN1(n395), .DIN2(n180), .Q(n394) );
  nor2s3 U289 ( .DIN1(n396), .DIN2(n467), .Q(n180) );
  and2s3 U290 ( .DIN1(n396), .DIN2(n467), .Q(n395) );
  and3s3 U291 ( .DIN1(n397), .DIN2(n396), .DIN3(G14), .Q(G118) );
  or2s3 U292 ( .DIN1(n398), .DIN2(n368), .Q(n396) );
  nnd2s3 U293 ( .DIN1(n368), .DIN2(n398), .Q(n397) );
  and3s3 U294 ( .DIN1(n399), .DIN2(n398), .DIN3(G14), .Q(G113) );
  nnd3s3 U295 ( .DIN1(n136), .DIN2(n137), .DIN3(n157), .Q(n398) );
  nnd2s3 U296 ( .DIN1(n377), .DIN2(n400), .Q(n399) );
  nnd2s3 U297 ( .DIN1(n157), .DIN2(n137), .Q(n400) );
  nor2s3 U298 ( .DIN1(n139), .DIN2(n401), .Q(G109) );
  xnr2s3 U299 ( .DIN1(n468), .DIN2(n157), .Q(n401) );
  nnd2s3 U300 ( .DIN1(n402), .DIN2(n403), .Q(n157) );
  nnd2s3 U301 ( .DIN1(n92), .DIN2(n404), .Q(n403) );
  nnd2s3 U302 ( .DIN1(n405), .DIN2(n406), .Q(n404) );
  nnd2s3 U303 ( .DIN1(n354), .DIN2(n407), .Q(n406) );
  or2s3 U304 ( .DIN1(n167), .DIN2(n408), .Q(n407) );
  nnd2s3 U305 ( .DIN1(n408), .DIN2(n167), .Q(n405) );
  nnd2s3 U306 ( .DIN1(n409), .DIN2(n410), .Q(n167) );
  nnd2s3 U307 ( .DIN1(n411), .DIN2(n107), .Q(n410) );
  or2s3 U308 ( .DIN1(n99), .DIN2(G3), .Q(n409) );
  nnd2s3 U309 ( .DIN1(n168), .DIN2(n412), .Q(n408) );
  nnd3s3 U310 ( .DIN1(n413), .DIN2(n414), .DIN3(n415), .Q(n412) );
  nnd2s3 U311 ( .DIN1(n416), .DIN2(n127), .Q(n415) );
  nnd3s3 U312 ( .DIN1(n417), .DIN2(n126), .DIN3(n418), .Q(n414) );
  nnd3s3 U313 ( .DIN1(n94), .DIN2(n128), .DIN3(n165), .Q(n413) );
  xnr2s3 U314 ( .DIN1(n419), .DIN2(n469), .Q(n165) );
  nnd2s3 U315 ( .DIN1(n420), .DIN2(n421), .Q(n419) );
  nnd2s3 U316 ( .DIN1(n411), .DIN2(n110), .Q(n421) );
  or2s3 U317 ( .DIN1(n99), .DIN2(G0), .Q(n420) );
  nor2s3 U318 ( .DIN1(n127), .DIN2(n416), .Q(n163) );
  and2s3 U319 ( .DIN1(n422), .DIN2(n423), .Q(n416) );
  nnd2s3 U320 ( .DIN1(n411), .DIN2(n109), .Q(n423) );
  or2s3 U321 ( .DIN1(n99), .DIN2(G1), .Q(n422) );
  nnd2s3 U322 ( .DIN1(n470), .DIN2(n424), .Q(n168) );
  nnd2s3 U323 ( .DIN1(n418), .DIN2(n417), .Q(n424) );
  or2s3 U324 ( .DIN1(n99), .DIN2(G2), .Q(n417) );
  nnd2s3 U325 ( .DIN1(n411), .DIN2(n108), .Q(n418) );
  xnr2s3 U326 ( .DIN1(n425), .DIN2(n357), .Q(n166) );
  nnd2s3 U327 ( .DIN1(n357), .DIN2(n425), .Q(n402) );
  nnd2s3 U328 ( .DIN1(n426), .DIN2(n427), .Q(n425) );
  nnd2s3 U329 ( .DIN1(n411), .DIN2(n106), .Q(n427) );
  and3s3 U330 ( .DIN1(n144), .DIN2(n99), .DIN3(n145), .Q(n411) );
  nnd3s3 U331 ( .DIN1(n428), .DIN2(n429), .DIN3(n370), .Q(n145) );
  nnd2s3 U332 ( .DIN1(G8), .DIN2(n378), .Q(n429) );
  nnd2s3 U333 ( .DIN1(n473), .DIN2(n99), .Q(n428) );
  nnd3s3 U334 ( .DIN1(n430), .DIN2(n431), .DIN3(n371), .Q(n144) );
  or2s3 U335 ( .DIN1(n99), .DIN2(G8), .Q(n431) );
  nnd2s3 U336 ( .DIN1(n99), .DIN2(n116), .Q(n430) );
  or2s3 U337 ( .DIN1(n99), .DIN2(G4), .Q(n426) );
  i1s3 U338 ( .DIN(n363), .Q(n75) );
  i1s3 U339 ( .DIN(n143), .Q(n76) );
  i1s3 U340 ( .DIN(n294), .Q(n77) );
  i1s3 U341 ( .DIN(n270), .Q(n78) );
  i1s3 U342 ( .DIN(n254), .Q(n79) );
  i1s3 U343 ( .DIN(n218), .Q(n80) );
  i1s3 U344 ( .DIN(n222), .Q(n81) );
  i1s3 U345 ( .DIN(n229), .Q(n82) );
  i1s3 U346 ( .DIN(n290), .Q(n83) );
  i1s3 U347 ( .DIN(n284), .Q( tempn84 ) );
  i1s3 U348 ( .DIN(n285), .Q(n85) );
  i1s3 U349 ( .DIN(n289), .Q(n86) );
  i1s3 U350 ( .DIN(n227), .Q(n87) );
  i1s3 U351 ( .DIN(n465), .Q(n88) );
  i1s3 U352 ( .DIN(n458), .Q(n89) );
  i1s3 U353 ( .DIN(n200), .Q(n90) );
  i1s3 U354 ( .DIN(n318), .Q(n91) );
  i1s3 U355 ( .DIN(n166), .Q(n92) );
  i1s3 U356 ( .DIN(n168), .Q(n93) );
  i1s3 U357 ( .DIN(n163), .Q(n94) );
  i1s3 U358 ( .DIN(n145), .Q(n95) );
  i1s3 U359 ( .DIN(n144), .Q(n96) );
  i1s3 U360 ( .DIN(n235), .Q(n97) );
  i1s3 U361 ( .DIN(n169), .Q(n98) );
  i1s3 U363 ( .DIN(n360), .Q(n100) );
  i1s3 U364 ( .DIN(n433), .Q(n101) );
  i1s3 U365 ( .DIN(n434), .Q(n102) );
  i1s3 U366 ( .DIN(n184), .Q(n103) );
  i1s3 U367 ( .DIN(n432), .Q(n104) );
  i1s3 U368 ( .DIN(n203), .Q(n105) );
  i1s3 U369 ( .DIN(n472), .Q(n106) );
  i1s3 U370 ( .DIN(n369), .Q(n107) );
  i1s3 U371 ( .DIN(n471), .Q(n108) );
  i1s3 U372 ( .DIN(n356), .Q(n109) );
  i1s3 U373 ( .DIN(n346), .Q(n110) );
  i1s3 U374 ( .DIN(n213), .Q(n111) );
  i1s3 U375 ( .DIN(n258), .Q(n112) );
  i1s3 U376 ( .DIN(n358), .Q(n113) );
  i1s3 U377 ( .DIN(n352), .Q(n114) );
  i1s3 U378 ( .DIN(n435), .Q(n115) );
  i1s3 U379 ( .DIN(n473), .Q(n116) );
  i1s3 U380 ( .DIN(n350), .Q(n117) );
  i1s3 U381 ( .DIN(n436), .Q(n118) );
  i1s3 U382 ( .DIN(n437), .Q(n119) );
  i1s3 U383 ( .DIN(n443), .Q(n120) );
  i1s3 U384 ( .DIN(n448), .Q(n121) );
  i1s3 U385 ( .DIN(n456), .Q(n122) );
  i1s3 U386 ( .DIN(n455), .Q(n123) );
  i1s3 U387 ( .DIN(n454), .Q(n124) );
  i1s3 U388 ( .DIN(n453), .Q(n125) );
  i1s3 U389 ( .DIN(n470), .Q(n126) );
  i1s3 U390 ( .DIN(n353), .Q(n127) );
  i1s3 U391 ( .DIN(n469), .Q(n128) );
  i1s3 U392 ( .DIN(n459), .Q(n129) );
  i1s3 U393 ( .DIN(n460), .Q(n130) );
  i1s3 U394 ( .DIN(n374), .Q(n131) );
  i1s3 U395 ( .DIN(n457), .Q(n132) );
  i1s3 U396 ( .DIN(n462), .Q(n133) );
  i1s3 U397 ( .DIN(n359), .Q(n134) );
  i1s3 U398 ( .DIN(n466), .Q(n135) );
  i1s3 U399 ( .DIN(n377), .Q(n136) );
  i1s3 U400 ( .DIN(n468), .Q(n137) );
  i1s3 U401 ( .DIN(G10), .Q(n138) );
  i1s3 U403 ( .DIN(G15), .Q(G701BF) );
  i1s3 U404 ( .DIN(G5), .Q(n141) );
  i1s3 U405 ( .DIN(G6), .Q(n142) );
  ib1s9 U406 ( .DIN(G14), .Q(n139) );
  ib1s5 U407 ( .DIN(n378), .Q(n99) );
  sdffs1 \DFF_73/Q_reg  ( .DIN(G713), .SDIN(n539), .SSEL(test_se), .CLK(CK), 
        .Q(G729) );
  sdffs1 \DFF_72/Q_reg  ( .DIN(G707), .SDIN(G726), .SSEL(test_se), .CLK(CK), 
        .Q(n539), .QN(n363) );
  sdffs1 \DFF_71/Q_reg  ( .DIN(G705), .SDIN(n538), .SSEL(test_se), .CLK(CK), 
        .Q(G726) );
  sdffs1 \DFF_70/Q_reg  ( .DIN(G693), .SDIN(n537), .SSEL(test_se), .CLK(CK), 
        .Q(n538), .QN(n465) );
  sdffs1 \DFF_69/Q_reg  ( .DIN(G687), .SDIN(n536), .SSEL(test_se), .CLK(CK), 
        .Q(n537), .QN(n458) );
  sdffs1 \DFF_68/Q_reg  ( .DIN(G682), .SDIN(n535), .SSEL(test_se), .CLK(CK), 
        .Q(n536), .QN(n378) );
  sdffs1 \DFF_67/Q_reg  ( .DIN(G675), .SDIN(n534), .SSEL(test_se), .CLK(CK), 
        .Q(n535), .QN(n360) );
  sdffs1 \DFF_66/Q_reg  ( .DIN(G669), .SDIN(n533), .SSEL(test_se), .CLK(CK), 
        .Q(n534), .QN(n433) );
  sdffs1 \DFF_65/Q_reg  ( .DIN(G663), .SDIN(n532), .SSEL(test_se), .CLK(CK), 
        .Q(n533), .QN(n434) );
  sdffs1 \DFF_64/Q_reg  ( .DIN(G657), .SDIN(n531), .SSEL(test_se), .CLK(CK), 
        .Q(n532), .QN(n432) );
  sdffs1 \DFF_63/Q_reg  ( .DIN(G613), .SDIN(n530), .SSEL(test_se), .CLK(CK), 
        .Q(n531), .QN(n370) );
  sdffs1 \DFF_62/Q_reg  ( .DIN(G608), .SDIN(n529), .SSEL(test_se), .CLK(CK), 
        .Q(n530), .QN(n371) );
  sdffs1 \DFF_61/Q_reg  ( .DIN(G590), .SDIN(n528), .SSEL(test_se), .CLK(CK), 
        .Q(n529), .QN(n345) );
  sdffs1 \DFF_60/Q_reg  ( .DIN(G577), .SDIN(n527), .SSEL(test_se), .CLK(CK), 
        .Q(n528), .QN(n444) );
  sdffs1 \DFF_59/Q_reg  ( .DIN(G573), .SDIN(n526), .SSEL(test_se), .CLK(CK), 
        .Q(n527), .QN(n445) );
  sdffs1 \DFF_58/Q_reg  ( .DIN(G569), .SDIN(n525), .SSEL(test_se), .CLK(CK), 
        .Q(n526), .QN(n446) );
  sdffs1 \DFF_57/Q_reg  ( .DIN(G565), .SDIN(n524), .SSEL(test_se), .CLK(CK), 
        .Q(n525), .QN(n447) );
  sdffs1 \DFF_56/Q_reg  ( .DIN(G548), .SDIN(n523), .SSEL(test_se), .CLK(CK), 
        .Q(n524), .QN(n472) );
  sdffs1 \DFF_55/Q_reg  ( .DIN(G541), .SDIN(n522), .SSEL(test_se), .CLK(CK), 
        .Q(n523), .QN(n369) );
  sdffs1 \DFF_54/Q_reg  ( .DIN(G536), .SDIN(n521), .SSEL(test_se), .CLK(CK), 
        .Q(n522), .QN(n471) );
  sdffs1 \DFF_53/Q_reg  ( .DIN(G531), .SDIN(n520), .SSEL(test_se), .CLK(CK), 
        .Q(n521), .QN(n356) );
  sdffs1 \DFF_52/Q_reg  ( .DIN(G526), .SDIN(n519), .SSEL(test_se), .CLK(CK), 
        .Q(n520), .QN(n346) );
  sdffs1 \DFF_51/Q_reg  ( .DIN(G503), .SDIN(n518), .SSEL(test_se), .CLK(CK), 
        .Q(n519), .QN(n452) );
  sdffs1 \DFF_50/Q_reg  ( .DIN(G498), .SDIN(n517), .SSEL(test_se), .CLK(CK), 
        .Q(n518), .QN(n451) );
  sdffs1 \DFF_49/Q_reg  ( .DIN(G494), .SDIN(n516), .SSEL(test_se), .CLK(CK), 
        .Q(n517), .QN(n450) );
  sdffs1 \DFF_48/Q_reg  ( .DIN(G477), .SDIN(n515), .SSEL(test_se), .CLK(CK), 
        .Q(n516), .QN(n372) );
  sdffs1 \DFF_47/Q_reg  ( .DIN(G469), .SDIN(n514), .SSEL(test_se), .CLK(CK), 
        .Q(n515), .QN(n351) );
  sdffs1 \DFF_46/Q_reg  ( .DIN(G464), .SDIN(n513), .SSEL(test_se), .CLK(CK), 
        .Q(n514), .QN(n358) );
  sdffs1 \DFF_45/Q_reg  ( .DIN(G459), .SDIN(n512), .SSEL(test_se), .CLK(CK), 
        .Q(n513), .QN(n352) );
  sdffs1 \DFF_44/Q_reg  ( .DIN(G451), .SDIN(n511), .SSEL(test_se), .CLK(CK), 
        .Q(n512), .QN(n366) );
  sdffs1 \DFF_43/Q_reg  ( .DIN(G447), .SDIN(n510), .SSEL(test_se), .CLK(CK), 
        .Q(n511), .QN(n435) );
  sdffs1 \DFF_42/Q_reg  ( .DIN(G441), .SDIN(n509), .SSEL(test_se), .CLK(CK), 
        .Q(n510), .QN(n473) );
  sdffs1 \DFF_41/Q_reg  ( .DIN(G438), .SDIN(n436), .SSEL(test_se), .CLK(CK), 
        .Q(n509), .QN(n350) );
  sdffs1 \DFF_40/Q_reg  ( .DIN(G427), .SDIN(n508), .SSEL(test_se), .CLK(CK), 
        .Q(n436) );
  sdffs1 \DFF_39/Q_reg  ( .DIN(G424), .SDIN(n507), .SSEL(test_se), .CLK(CK), 
        .Q(n508), .QN(n437) );
  sdffs1 \DFF_38/Q_reg  ( .DIN(G416), .SDIN(n506), .SSEL(test_se), .CLK(CK), 
        .Q(n507), .QN(n438) );
  sdffs1 \DFF_37/Q_reg  ( .DIN(G408), .SDIN(n505), .SSEL(test_se), .CLK(CK), 
        .Q(n506), .QN(n361) );
  sdffs1 \DFF_36/Q_reg  ( .DIN(G405), .SDIN(n504), .SSEL(test_se), .CLK(CK), 
        .Q(n505), .QN(n443) );
  sdffs1 \DFF_35/Q_reg  ( .DIN(G397), .SDIN(n503), .SSEL(test_se), .CLK(CK), 
        .Q(n504), .QN(n439) );
  sdffs1 \DFF_34/Q_reg  ( .DIN(G392), .SDIN(n502), .SSEL(test_se), .CLK(CK), 
        .Q(n503), .QN(n448) );
  sdffs1 \DFF_33/Q_reg  ( .DIN(G384), .SDIN(n501), .SSEL(test_se), .CLK(CK), 
        .Q(n502), .QN(n440) );
  sdffs1 \DFF_32/Q_reg  ( .DIN(G379), .SDIN(n500), .SSEL(test_se), .CLK(CK), 
        .Q(n501), .QN(n449) );
  sdffs1 \DFF_31/Q_reg  ( .DIN(G373), .SDIN(n499), .SSEL(test_se), .CLK(CK), 
        .Q(n500), .QN(n442) );
  sdffs1 \DFF_30/Q_reg  ( .DIN(G365), .SDIN(n498), .SSEL(test_se), .CLK(CK), 
        .Q(n499), .QN(n373) );
  sdffs1 \DFF_29/Q_reg  ( .DIN(G360), .SDIN(n497), .SSEL(test_se), .CLK(CK), 
        .Q(n498), .QN(n441) );
  sdffs1 \DFF_28/Q_reg  ( .DIN(G321), .SDIN(n496), .SSEL(test_se), .CLK(CK), 
        .Q(n497), .QN(n456) );
  sdffs1 \DFF_27/Q_reg  ( .DIN(G315), .SDIN(n495), .SSEL(test_se), .CLK(CK), 
        .Q(n496), .QN(n455) );
  sdffs1 \DFF_26/Q_reg  ( .DIN(G309), .SDIN(n494), .SSEL(test_se), .CLK(CK), 
        .Q(n495), .QN(n454) );
  sdffs1 \DFF_25/Q_reg  ( .DIN(G303), .SDIN(n493), .SSEL(test_se), .CLK(CK), 
        .Q(n494), .QN(n453) );
  sdffs1 \DFF_24/Q_reg  ( .DIN(G260), .SDIN(n492), .SSEL(test_se), .CLK(CK), 
        .Q(n493), .QN(n357) );
  sdffs1 \DFF_23/Q_reg  ( .DIN(G252), .SDIN(n491), .SSEL(test_se), .CLK(CK), 
        .Q(n492), .QN(n354) );
  sdffs1 \DFF_22/Q_reg  ( .DIN(G247), .SDIN(n490), .SSEL(test_se), .CLK(CK), 
        .Q(n491), .QN(n470) );
  sdffs1 \DFF_21/Q_reg  ( .DIN(G242), .SDIN(n489), .SSEL(test_se), .CLK(CK), 
        .Q(n490), .QN(n353) );
  sdffs1 \DFF_20/Q_reg  ( .DIN(G237), .SDIN(n488), .SSEL(test_se), .CLK(CK), 
        .Q(n489), .QN(n469) );
  sdffs1 \DFF_19/Q_reg  ( .DIN(G218), .SDIN(n460), .SSEL(test_se), .CLK(CK), 
        .Q(n488), .QN(n459) );
  sdffs1 \DFF_18/Q_reg  ( .DIN(G214), .SDIN(n487), .SSEL(test_se), .CLK(CK), 
        .Q(n460) );
  sdffs1 \DFF_17/Q_reg  ( .DIN(G208), .SDIN(n486), .SSEL(test_se), .CLK(CK), 
        .Q(n487), .QN(n461) );
  sdffs1 \DFF_16/Q_reg  ( .DIN(G198), .SDIN(n485), .SSEL(test_se), .CLK(CK), 
        .Q(n486), .QN(n364) );
  sdffs1 \DFF_15/Q_reg  ( .DIN(G193), .SDIN(n457), .SSEL(test_se), .CLK(CK), 
        .Q(n485), .QN(n374) );
  sdffs1 \DFF_14/Q_reg  ( .DIN(G189), .SDIN(n484), .SSEL(test_se), .CLK(CK), 
        .Q(n457) );
  sdffs1 \DFF_13/Q_reg  ( .DIN(G175), .SDIN(n483), .SSEL(test_se), .CLK(CK), 
        .Q(n484), .QN(n462) );
  sdffs1 \DFF_12/Q_reg  ( .DIN(G166), .SDIN(n482), .SSEL(test_se), .CLK(CK), 
        .Q(n483), .QN(n359) );
  sdffs1 \DFF_11/Q_reg  ( .DIN(G159), .SDIN(n481), .SSEL(test_se), .CLK(CK), 
        .Q(n482), .QN(n367) );
  sdffs1 \DFF_10/Q_reg  ( .DIN(G154), .SDIN(n480), .SSEL(test_se), .CLK(CK), 
        .Q(n481), .QN(n375) );
  sdffs1 \DFF_9/Q_reg  ( .DIN(G149), .SDIN(n479), .SSEL(test_se), .CLK(CK), 
        .Q(n480), .QN(n463) );
  sdffs1 \DFF_8/Q_reg  ( .DIN(G144), .SDIN(n464), .SSEL(test_se), .CLK(CK), 
        .Q(n479), .QN(n376) );
  sdffs1 \DFF_7/Q_reg  ( .DIN(G140), .SDIN(n478), .SSEL(test_se), .CLK(CK), 
        .Q(n464) );
  sdffs1 \DFF_6/Q_reg  ( .DIN(G129), .SDIN(n467), .SSEL(test_se), .CLK(CK), 
        .Q(n478), .QN(n466) );
  sdffs1 \DFF_5/Q_reg  ( .DIN(G125), .SDIN(n477), .SSEL(test_se), .CLK(CK), 
        .Q(n467) );
  sdffs1 \DFF_4/Q_reg  ( .DIN(G118), .SDIN(n476), .SSEL(test_se), .CLK(CK), 
        .Q(n477), .QN(n368) );
  sdffs1 \DFF_3/Q_reg  ( .DIN(G113), .SDIN(n468), .SSEL(test_se), .CLK(CK), 
        .Q(n476), .QN(n377) );
  sdffs1 \DFF_2/Q_reg  ( .DIN(G109), .SDIN(G23), .SSEL(test_se), .CLK(CK), .Q(
        n468) );
  sdffs1 \DFF_1/Q_reg  ( .DIN(G328BF), .SDIN(G22), .SSEL(test_se), .CLK(CK), 
        .Q(G23) );
  sdffs1 \DFF_0/Q_reg  ( .DIN(G332BF), .SDIN(test_si), .SSEL(test_se), .CLK(CK), .Q(G22) );
  nor2s1 trig47_0U1 ( .DIN1(trig47_0n1), .DIN2(trig47_0n2), .Q(Trigger_en0_0) );
  nnd4s1 trig47_0U2 ( .DIN1(n164), .DIN2(trig47_0n3), .DIN3(n82), .DIN4(trig47_0n4), .Q(trig47_0n2) );
  nor3s1 trig47_0U3 ( .DIN1(n120), .DIN2(n168), .DIN3(n127), .Q(trig47_0n4) );
  i1s1 trig47_0U4 ( .DIN(G328BF), .Q(trig47_0n3) );
  or5s1 trig47_0U5 ( .DIN1(n249), .DIN2(n197), .DIN3(n189), .DIN4(n298), .DIN5(trig47_0n5),         .Q(trig47_0n1) );
  i1s1 trig47_0U6 ( .DIN(trig47_0n6), .Q(trig47_0n5) );
  nor2s1 trig47_0U7 ( .DIN1(n315), .DIN2(n306), .Q(trig47_0n6) );
  dffles2 troj19_0state_reg_0_ ( .DIN(troj19_0N90), .EB(troj19_0n9), .CLK(CK), .Q(troj19_0state_0_), .QN(troj19_0n11)         );
  dffles2 troj19_0state_reg_2_ ( .DIN(troj19_0N92), .EB(troj19_0n9), .CLK(CK), .Q(troj19_0state_2_), .QN(troj19_0n22)         );
  dffles2 troj19_0state_reg_1_ ( .DIN(troj19_0N91), .EB(troj19_0n9), .CLK(CK), .Q(troj19_0state_1_), .QN(troj19_0n14)         );
  dffles2 troj19_0state_reg_3_ ( .DIN(troj19_0N93), .EB(troj19_0n9), .CLK(CK), .Q(troj19_0state_3_), .QN(troj19_0n10)         );
  dffles2 troj19_0Trojan_out0_reg ( .DIN(troj19_0N88), .EB(troj19_0n8), .CLK(CK), .Q(Trojan_out0) );
  and2s2 troj19_0U3 ( .DIN1(troj19_0state_2_), .DIN2(troj19_0state_3_), .Q(troj19_0n1) );
  ib1s2 troj19_0U4 ( .DIN(Trigger_en0_0), .Q(troj19_0n2) );
  xor2s2 troj19_0U5 ( .DIN1(troj19_0state_3_), .DIN2(troj19_0state_2_), .Q(troj19_0n3) );
  mxi21s3 troj19_0U6 ( .DIN1(troj19_0n4), .DIN2(troj19_0n5), .SIN(troj19_0state_0_), .Q(troj19_0N89) );
  or2s2 troj19_0U7 ( .DIN1(troj19_0state_1_), .DIN2(troj19_0n2), .Q(troj19_0n6) );
  ib1s2 troj19_0U8 ( .DIN(troj19_0n6), .Q(troj19_0n7) );
  mxi21s3 troj19_0U9 ( .DIN1(Trigger_en0_0), .DIN2(troj19_0n7), .SIN(troj19_0n1), .Q(troj19_0n5) );
  ib1s2 troj19_0U10 ( .DIN(troj19_0n5), .Q(troj19_0N87) );
  mxi21s3 troj19_0U11 ( .DIN1(troj19_0n7), .DIN2(Trigger_en0_0), .SIN(troj19_0n3), .Q(troj19_0n4) );
  ib1s1 troj19_0U12 ( .DIN(troj19_0N87), .Q(troj19_0n8) );
  ib1s1 troj19_0U13 ( .DIN(troj19_0N89), .Q(troj19_0n9) );
  oai221s2 troj19_0U14 ( .DIN1(troj19_0state_2_), .DIN2(troj19_0n10), .DIN3(troj19_0n11), .DIN4(troj19_0n12), .DIN5(troj19_0n13), .Q(troj19_0N93) );
  aoi21s3 troj19_0U15 ( .DIN1(troj19_0state_3_), .DIN2(troj19_0state_0_), .DIN3(troj19_0n17), .Q(troj19_0n15) );
  nnd2s2 troj19_0U16 ( .DIN1(troj19_0n18), .DIN2(troj19_0n16), .Q(troj19_0N91) );
  oai21s3 troj19_0U17 ( .DIN1(troj19_0state_0_), .DIN2(troj19_0n19), .DIN3(troj19_0n10), .Q(troj19_0n18) );
  ib1s2 troj19_0U18 ( .DIN(troj19_0n12), .Q(troj19_0n19) );
  oai1112s2 troj19_0U19 ( .DIN4(troj19_0state_0_), .DIN5(troj19_0n12), .DIN1(troj19_0n20), .DIN2(troj19_0n21), .DIN3(troj19_0n16), .Q(troj19_0N90) );
  nnd4s2 troj19_0U20 ( .DIN1(troj19_0state_3_), .DIN2(troj19_0state_2_), .DIN3(troj19_0n11), .DIN4(troj19_0n14), .Q(troj19_0n16) );
  nnd4s2 troj19_0U21 ( .DIN1(troj19_0state_3_), .DIN2(troj19_0state_0_), .DIN3(troj19_0state_1_), .DIN4(troj19_0n22),         .Q(troj19_0n21) );
  nor2s2 troj19_0U22 ( .DIN1(troj19_0n17), .DIN2(troj19_0n23), .Q(troj19_0n20) );
  ib1s2 troj19_0U23 ( .DIN(troj19_0n13), .Q(troj19_0n23) );
  nnd4s2 troj19_0U24 ( .DIN1(troj19_0state_0_), .DIN2(troj19_0state_2_), .DIN3(troj19_0state_1_), .DIN4(troj19_0n10),         .Q(troj19_0n13) );
  and3s2 troj19_0U25 ( .DIN1(troj19_0n11), .DIN2(troj19_0n10), .DIN3(troj19_0state_2_), .Q(troj19_0n17) );
  nnd2s2 troj19_0U26 ( .DIN1(troj19_0n14), .DIN2(troj19_0n22), .Q(troj19_0n12) );
  and4s2 troj19_0U27 ( .DIN1(troj19_0state_1_), .DIN2(troj19_0n11), .DIN3(troj19_0n22), .DIN4(troj19_0n10), .Q(troj19_0N88) );
  oai321s1 troj19_0U28 ( .DIN1(troj19_0n11), .DIN2(troj19_0state_2_), .DIN3(troj19_0n14), .DIN4(troj19_0state_1_),         .DIN5(troj19_0n15), .DIN6(troj19_0n16), .Q(troj19_0N92) );
    xor2s1 trojan19_0  (.DIN1(tempn224), .DIN2(Trojan_out0), .Q(n224) );
  nor2s1 troj19_1U1 ( .DIN1(troj19_1n1), .DIN2(troj19_1n2), .Q(Trigger_en1_19) );
  i1s1 troj19_1U2 ( .DIN(troj19_1n3), .Q(troj19_1n2) );
  and4s1 troj19_1U3 ( .DIN1(n227), .DIN2(n181), .DIN3(troj19_1n4), .DIN4(n180), .Q(troj19_1n3) );
  nor2s1 troj19_1U4 ( .DIN1(n257), .DIN2(n162), .Q(troj19_1n4) );
  or5s1 troj19_1U5 ( .DIN1(n396), .DIN2(n392), .DIN3(n340), .DIN4(n299), .DIN5(n277),         .Q(troj19_1n1) );
    xor2s1 trojan19_1  (.DIN1(tempn84), .DIN2(Trigger_en1_19), .Q(n84) );

endmodule

