; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@a = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@b = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@p = dso_local global [24 x i32] zeroinitializer, align 16
define dso_local noundef i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  store i32 0, i32* %5, align 4
  store i32 0, i32* %1, align 4
  %6 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 0
  %7 = getelementptr inbounds [24 x i32], [24 x i32]* %6, i64 0, i64 0
  %8 = load i32, i32* %7, align 4
  %9 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 0
  %10 = getelementptr inbounds [24 x i32], [24 x i32]* %9, i64 0, i64 0
  %11 = load i32, i32* %10, align 4
  %12 = mul nsw i32 %8, %11
  %13 = getelementptr inbounds [24 x i32], [24 x i32]* @p, i64 0, i64 0
  store i32 %12, i32* %13, align 4
  store i32 0, i32* %2, align 4
  br label %14

14:
  %15 = load i32, i32* %2, align 4
  %16 = icmp slt i32 %15, 24
  br i1 %16, label %17, label %38

17:
  store i32 0, i32* %3, align 4
  br label %18

18:
  %19 = load i32, i32* %3, align 4
  %20 = icmp slt i32 %19, 24
  br i1 %20, label %21, label %35

21:
  store i32 0, i32* %4, align 4
  br label %22

22:
  %23 = load i32, i32* %4, align 4
  %24 = icmp slt i32 %23, 24
  br i1 %24, label %25, label %32

25:
  %26 = load i32, i32* %5, align 4
  %27 = load i32, i32* %4, align 4
  %28 = add nsw i32 %26, %27
  store i32 %28, i32* %5, align 4
  br label %29

29:
  %30 = load i32, i32* %4, align 4
  %31 = add nsw i32 %30, 1
  store i32 %31, i32* %4, align 4
  br label %22

32:
  %33 = load i32, i32* %3, align 4
  %34 = add nsw i32 %33, 1
  store i32 %34, i32* %3, align 4
  br label %18

35:
  %36 = load i32, i32* %2, align 4
  %37 = add nsw i32 %36, 1
  store i32 %37, i32* %2, align 4
  br label %14

38:
  %39 = getelementptr inbounds [24 x i32], [24 x i32]* @p, i64 0, i64 0
  %40 = load i32, i32* %39, align 4
  %41 = load i32, i32* %5, align 4
  %42 = add nsw i32 %40, %41
  %43 = getelementptr inbounds [24 x i32], [24 x i32]* @p, i64 0, i64 1
  store i32 %42, i32* %43, align 4
  %44 = load i32, i32* %1, align 4
  ret i32 %44
}
attributes #0 = { nounwind }
