; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
define dso_local noundef i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  %6 = alloca i32, align 4
  store i32 0, i32* %6, align 4
  store i32 0, i32* %1, align 4
  store i32 3, i32* %5, align 4
  %7 = load i32, i32* %5, align 4
  %8 = mul nsw i32 %7, 5
  store i32 %8, i32* %5, align 4
  store i32 0, i32* %2, align 4
  br label %9

9:
  %10 = load i32, i32* %2, align 4
  %11 = icmp slt i32 %10, 24
  br i1 %11, label %12, label %33

12:
  store i32 0, i32* %3, align 4
  br label %13

13:
  %14 = load i32, i32* %3, align 4
  %15 = icmp slt i32 %14, 24
  br i1 %15, label %16, label %30

16:
  store i32 0, i32* %4, align 4
  br label %17

17:
  %18 = load i32, i32* %4, align 4
  %19 = icmp slt i32 %18, 24
  br i1 %19, label %20, label %27

20:
  %21 = load i32, i32* %6, align 4
  %22 = load i32, i32* %4, align 4
  %23 = add nsw i32 %21, %22
  store i32 %23, i32* %6, align 4
  br label %24

24:
  %25 = load i32, i32* %4, align 4
  %26 = add nsw i32 %25, 1
  store i32 %26, i32* %4, align 4
  br label %17

27:
  %28 = load i32, i32* %3, align 4
  %29 = add nsw i32 %28, 1
  store i32 %29, i32* %3, align 4
  br label %13

30:
  %31 = load i32, i32* %2, align 4
  %32 = add nsw i32 %31, 1
  store i32 %32, i32* %2, align 4
  br label %9

33:
  %34 = load i32, i32* %5, align 4
  %35 = load i32, i32* %6, align 4
  %36 = add nsw i32 %34, %35
  store i32 %36, i32* %5, align 4
  %37 = load i32, i32* %1, align 4
  ret i32 %37
}
attributes #0 = { nounwind }
