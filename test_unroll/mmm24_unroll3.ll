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
  br i1 %7, label %8, label %91

8:
  store i32 0, i32* %3, align 4
  br label %9

9:
  %10 = load i32, i32* %3, align 4
  %11 = icmp slt i32 %10, 24
  br i1 %11, label %12, label %88

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
  br i1 %21, label %22, label %85

22:
  %23 = load i32, i32* %2, align 4
  %24 = sext i32 %23 to i64
  %25 = load i32, i32* %4, align 4
  %26 = sext i32 %25 to i64
  %27 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %24
  %28 = getelementptr inbounds [24 x i32], [24 x i32]* %27, i64 0, i64 %26
  %29 = load i32, i32* %28, align 4
  %30 = load i32, i32* %4, align 4
  %31 = sext i32 %30 to i64
  %32 = load i32, i32* %3, align 4
  %33 = sext i32 %32 to i64
  %34 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %31
  %35 = getelementptr inbounds [24 x i32], [24 x i32]* %34, i64 0, i64 %33
  %36 = load i32, i32* %35, align 4
  %37 = mul nsw i32 %29, %36
  %38 = load i32, i32* %2, align 4
  %39 = sext i32 %38 to i64
  %40 = load i32, i32* %4, align 4
  %41 = add nsw i32 %40, 1
  %42 = sext i32 %41 to i64
  %43 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %39
  %44 = getelementptr inbounds [24 x i32], [24 x i32]* %43, i64 0, i64 %42
  %45 = load i32, i32* %44, align 4
  %46 = load i32, i32* %4, align 4
  %47 = add nsw i32 %46, 1
  %48 = sext i32 %47 to i64
  %49 = load i32, i32* %3, align 4
  %50 = sext i32 %49 to i64
  %51 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %48
  %52 = getelementptr inbounds [24 x i32], [24 x i32]* %51, i64 0, i64 %50
  %53 = load i32, i32* %52, align 4
  %54 = mul nsw i32 %45, %53
  %55 = load i32, i32* %2, align 4
  %56 = sext i32 %55 to i64
  %57 = load i32, i32* %4, align 4
  %58 = add nsw i32 %57, 2
  %59 = sext i32 %58 to i64
  %60 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %56
  %61 = getelementptr inbounds [24 x i32], [24 x i32]* %60, i64 0, i64 %59
  %62 = load i32, i32* %61, align 4
  %63 = load i32, i32* %4, align 4
  %64 = add nsw i32 %63, 2
  %65 = sext i32 %64 to i64
  %66 = load i32, i32* %3, align 4
  %67 = sext i32 %66 to i64
  %68 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %65
  %69 = getelementptr inbounds [24 x i32], [24 x i32]* %68, i64 0, i64 %67
  %70 = load i32, i32* %69, align 4
  %71 = mul nsw i32 %62, %70
  %72 = add nsw i32 %37, %54
  %73 = add nsw i32 %72, %71
  %74 = load i32, i32* %2, align 4
  %75 = sext i32 %74 to i64
  %76 = load i32, i32* %3, align 4
  %77 = sext i32 %76 to i64
  %78 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %75
  %79 = getelementptr inbounds [24 x i32], [24 x i32]* %78, i64 0, i64 %77
  %80 = load i32, i32* %79, align 4
  %81 = add nsw i32 %80, %73
  store i32 %81, i32* %79, align 4
  br label %82

82:
  %83 = load i32, i32* %4, align 4
  %84 = add nsw i32 %83, 3
  store i32 %84, i32* %4, align 4
  br label %19

85:
  %86 = load i32, i32* %3, align 4
  %87 = add nsw i32 %86, 1
  store i32 %87, i32* %3, align 4
  br label %9

88:
  %89 = load i32, i32* %2, align 4
  %90 = add nsw i32 %89, 1
  store i32 %90, i32* %2, align 4
  br label %5

91:
  %92 = load i32, i32* %1, align 4
  ret i32 %92
}
attributes #0 = { nounwind }
