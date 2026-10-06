; counter %2 = %i1
; counter %3 = %i2
; counter %4 = %i3
%1 = alloca i32, align 4

; block entry
store i32 0, i32* %1, align 4

; block 12
store i32 0, i32* %gep_c_12_0, align 4

; block 22
%load_a_22_0 = load i32, i32* %gep_a_22_0, align 4
%load_b_22_0 = load i32, i32* %gep_b_22_0, align 4
%load_c_22_0 = load i32, i32* %gep_c_22_0, align 4
%37 = mul i32 %load_a_22_0, %load_b_22_0
%45 = add i32 %load_c_22_0, %37
store i32 %45, i32* %gep_c_22_0, align 4

; block 55
%56 = load i32, i32* %1, align 4
ret i32 %56
