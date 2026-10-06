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
  br i1 %7, label %8, label %61

8:
  store i32 0, i32* %3, align 4
  br label %9

9:
  %10 = load i32, i32* %3, align 4
  %11 = icmp slt i32 %10, 24
  br i1 %11, label %12, label %58

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
  br i1 %21, label %22, label %55

22:
  %23 = load i32, i32* %4, align 4
  %24 = srem i32 %23, 2
  %25 = icmp eq i32 %24, 1
  br i1 %25, label %26, label %29

26:
  %27 = load i32, i32* %4, align 4
  %28 = add nsw i32 %27, 1
  store i32 %28, i32* %4, align 4
  br label %19

29:
  %30 = load i32, i32* %2, align 4
  %31 = sext i32 %30 to i64
  %32 = load i32, i32* %4, align 4
  %33 = sext i32 %32 to i64
  %34 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %31
  %35 = getelementptr inbounds [24 x i32], [24 x i32]* %34, i64 0, i64 %33
  %36 = load i32, i32* %35, align 4
  %37 = load i32, i32* %4, align 4
  %38 = sext i32 %37 to i64
  %39 = load i32, i32* %3, align 4
  %40 = sext i32 %39 to i64
  %41 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %38
  %42 = getelementptr inbounds [24 x i32], [24 x i32]* %41, i64 0, i64 %40
  %43 = load i32, i32* %42, align 4
  %44 = mul nsw i32 %36, %43
  %45 = load i32, i32* %2, align 4
  %46 = sext i32 %45 to i64
  %47 = load i32, i32* %3, align 4
  %48 = sext i32 %47 to i64
  %49 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %46
  %50 = getelementptr inbounds [24 x i32], [24 x i32]* %49, i64 0, i64 %48
  %51 = load i32, i32* %50, align 4
  %52 = add nsw i32 %51, %44
  store i32 %52, i32* %50, align 4
  %53 = load i32, i32* %4, align 4
  %54 = add nsw i32 %53, 1
  store i32 %54, i32* %4, align 4
  br label %19

55:
  %56 = load i32, i32* %3, align 4
  %57 = add nsw i32 %56, 1
  store i32 %57, i32* %3, align 4
  br label %9

58:
  %59 = load i32, i32* %2, align 4
  %60 = add nsw i32 %59, 1
  store i32 %60, i32* %2, align 4
  br label %5

61:
  %62 = load i32, i32* %1, align 4
  ret i32 %62
}
attributes #0 = { nounwind }
