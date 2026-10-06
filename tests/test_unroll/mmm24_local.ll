; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@a = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@b = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@c = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
define dso_local noundef i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  %5 = alloca [24 x i32], align 16
  store i32 0, i32* %1, align 4
  store i32 0, i32* %2, align 4
  br label %6

6:
  %7 = load i32, i32* %2, align 4
  %8 = icmp slt i32 %7, 24
  br i1 %8, label %9, label %60

9:
  store i32 0, i32* %3, align 4
  br label %10

10:
  %11 = load i32, i32* %3, align 4
  %12 = icmp slt i32 %11, 24
  br i1 %12, label %13, label %57

13:
  %14 = load i32, i32* %2, align 4
  %15 = sext i32 %14 to i64
  %16 = load i32, i32* %3, align 4
  %17 = sext i32 %16 to i64
  %18 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %15
  %19 = getelementptr inbounds [24 x i32], [24 x i32]* %18, i64 0, i64 %17
  store i32 0, i32* %19, align 4
  store i32 0, i32* %4, align 4
  br label %20

20:
  %21 = load i32, i32* %4, align 4
  %22 = icmp slt i32 %21, 24
  br i1 %22, label %23, label %54

23:
  %24 = load i32, i32* %2, align 4
  %25 = sext i32 %24 to i64
  %26 = load i32, i32* %4, align 4
  %27 = sext i32 %26 to i64
  %28 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %25
  %29 = getelementptr inbounds [24 x i32], [24 x i32]* %28, i64 0, i64 %27
  %30 = load i32, i32* %29, align 4
  %31 = load i32, i32* %4, align 4
  %32 = sext i32 %31 to i64
  %33 = getelementptr inbounds [24 x i32], [24 x i32]* %5, i64 0, i64 %32
  store i32 %30, i32* %33, align 4
  %34 = load i32, i32* %33, align 4
  %35 = load i32, i32* %4, align 4
  %36 = sext i32 %35 to i64
  %37 = load i32, i32* %3, align 4
  %38 = sext i32 %37 to i64
  %39 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %36
  %40 = getelementptr inbounds [24 x i32], [24 x i32]* %39, i64 0, i64 %38
  %41 = load i32, i32* %40, align 4
  %42 = mul nsw i32 %34, %41
  %43 = load i32, i32* %2, align 4
  %44 = sext i32 %43 to i64
  %45 = load i32, i32* %3, align 4
  %46 = sext i32 %45 to i64
  %47 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %44
  %48 = getelementptr inbounds [24 x i32], [24 x i32]* %47, i64 0, i64 %46
  %49 = load i32, i32* %48, align 4
  %50 = add nsw i32 %49, %42
  store i32 %50, i32* %48, align 4
  br label %51

51:
  %52 = load i32, i32* %4, align 4
  %53 = add nsw i32 %52, 1
  store i32 %53, i32* %4, align 4
  br label %20

54:
  %55 = load i32, i32* %3, align 4
  %56 = add nsw i32 %55, 1
  store i32 %56, i32* %3, align 4
  br label %10

57:
  %58 = load i32, i32* %2, align 4
  %59 = add nsw i32 %58, 1
  store i32 %59, i32* %2, align 4
  br label %6

60:
  %61 = load i32, i32* %1, align 4
  ret i32 %61
}
attributes #0 = { nounwind }
