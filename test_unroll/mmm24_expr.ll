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
  store i32 0, i32* %1, align 4
  store i32 0, i32* %2, align 4
  br label %5

5:
  %6 = load i32, i32* %2, align 4
  %7 = icmp slt i32 %6, 24
  br i1 %7, label %8, label %58

8:
  store i32 0, i32* %3, align 4
  br label %9

9:
  %10 = load i32, i32* %3, align 4
  %11 = icmp slt i32 %10, 24
  br i1 %11, label %12, label %55

12:
  %13 = load i32, i32* %2, align 4
  %14 = sext i32 %13 to i64
  %15 = load i32, i32* %3, align 4
  %16 = sext i32 %15 to i64
  %17 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %14
  %18 = getelementptr inbounds [24 x i32], [24 x i32]* %17, i64 0, i64 %16
  store i32 0, i32* %18, align 4
  store i32 0, i32* %4, align 4
  br label %19

19:
  %20 = load i32, i32* %4, align 4
  %21 = icmp slt i32 %20, 24
  br i1 %21, label %22, label %52

22:
  %23 = load i32, i32* %2, align 4
  %24 = sext i32 %23 to i64
  %25 = load i32, i32* %4, align 4
  %26 = sext i32 %25 to i64
  %27 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %24
  %28 = getelementptr inbounds [24 x i32], [24 x i32]* %27, i64 0, i64 %26
  %29 = load i32, i32* %28, align 4
  %30 = load i32, i32* %4, align 4
  %31 = load i32, i32* %3, align 4
  %32 = add nsw i32 %30, %31
  %33 = srem i32 %32, 24
  %34 = sext i32 %33 to i64
  %35 = load i32, i32* %3, align 4
  %36 = sext i32 %35 to i64
  %37 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %34
  %38 = getelementptr inbounds [24 x i32], [24 x i32]* %37, i64 0, i64 %36
  %39 = load i32, i32* %38, align 4
  %40 = mul nsw i32 %29, %39
  %41 = load i32, i32* %2, align 4
  %42 = sext i32 %41 to i64
  %43 = load i32, i32* %3, align 4
  %44 = sext i32 %43 to i64
  %45 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %42
  %46 = getelementptr inbounds [24 x i32], [24 x i32]* %45, i64 0, i64 %44
  %47 = load i32, i32* %46, align 4
  %48 = add nsw i32 %47, %40
  store i32 %48, i32* %46, align 4
  br label %49

49:
  %50 = load i32, i32* %4, align 4
  %51 = add nsw i32 %50, 1
  store i32 %51, i32* %4, align 4
  br label %19

52:
  %53 = load i32, i32* %3, align 4
  %54 = add nsw i32 %53, 1
  store i32 %54, i32* %3, align 4
  br label %9

55:
  %56 = load i32, i32* %2, align 4
  %57 = add nsw i32 %56, 1
  store i32 %57, i32* %2, align 4
  br label %5

58:
  %59 = load i32, i32* %1, align 4
  ret i32 %59
}
attributes #0 = { nounwind }
