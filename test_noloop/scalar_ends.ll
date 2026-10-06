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
  %5 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  store i32 3, i32* %5, align 4
  %6 = load i32, i32* %5, align 4
  %7 = mul nsw i32 %6, 5
  store i32 %7, i32* %5, align 4
  store i32 0, i32* %2, align 4
  br label %8

8:
  %9 = load i32, i32* %2, align 4
  %10 = icmp slt i32 %9, 24
  br i1 %10, label %11, label %60

11:
  store i32 0, i32* %3, align 4
  br label %12

12:
  %13 = load i32, i32* %3, align 4
  %14 = icmp slt i32 %13, 24
  br i1 %14, label %15, label %57

15:
  %16 = load i32, i32* %2, align 4
  %17 = sext i32 %16 to i64
  %18 = load i32, i32* %3, align 4
  %19 = sext i32 %18 to i64
  %20 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %17
  %21 = getelementptr inbounds [24 x i32], [24 x i32]* %20, i64 0, i64 %19
  store i32 0, i32* %21, align 4
  store i32 0, i32* %4, align 4
  br label %22

22:
  %23 = load i32, i32* %4, align 4
  %24 = icmp slt i32 %23, 24
  br i1 %24, label %25, label %54

25:
  %26 = load i32, i32* %2, align 4
  %27 = sext i32 %26 to i64
  %28 = load i32, i32* %4, align 4
  %29 = sext i32 %28 to i64
  %30 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %27
  %31 = getelementptr inbounds [24 x i32], [24 x i32]* %30, i64 0, i64 %29
  %32 = load i32, i32* %31, align 4
  %33 = load i32, i32* %4, align 4
  %34 = sext i32 %33 to i64
  %35 = load i32, i32* %3, align 4
  %36 = sext i32 %35 to i64
  %37 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %34
  %38 = getelementptr inbounds [24 x i32], [24 x i32]* %37, i64 0, i64 %36
  %39 = load i32, i32* %38, align 4
  %40 = mul nsw i32 %32, %39
  %41 = load i32, i32* %5, align 4
  %42 = mul nsw i32 %40, %41
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
  br label %22

54:
  %55 = load i32, i32* %3, align 4
  %56 = add nsw i32 %55, 1
  store i32 %56, i32* %3, align 4
  br label %12

57:
  %58 = load i32, i32* %2, align 4
  %59 = add nsw i32 %58, 1
  store i32 %59, i32* %2, align 4
  br label %8

60:
  %61 = load i32, i32* %5, align 4
  %62 = add nsw i32 %61, 1
  store i32 %62, i32* %5, align 4
  %63 = load i32, i32* %1, align 4
  ret i32 %63
}
attributes #0 = { nounwind }
