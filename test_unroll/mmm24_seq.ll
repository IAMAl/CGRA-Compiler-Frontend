; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@a = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@b = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@c = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@d = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@e = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@f = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
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
  br i1 %7, label %8, label %55

8:
  store i32 0, i32* %3, align 4
  br label %9

9:
  %10 = load i32, i32* %3, align 4
  %11 = icmp slt i32 %10, 24
  br i1 %11, label %12, label %52

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
  br i1 %21, label %22, label %49

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
  %40 = load i32, i32* %3, align 4
  %41 = sext i32 %40 to i64
  %42 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %39
  %43 = getelementptr inbounds [24 x i32], [24 x i32]* %42, i64 0, i64 %41
  %44 = load i32, i32* %43, align 4
  %45 = add nsw i32 %44, %37
  store i32 %45, i32* %43, align 4
  br label %46

46:
  %47 = load i32, i32* %4, align 4
  %48 = add nsw i32 %47, 1
  store i32 %48, i32* %4, align 4
  br label %19

49:
  %50 = load i32, i32* %3, align 4
  %51 = add nsw i32 %50, 1
  store i32 %51, i32* %3, align 4
  br label %9

52:
  %53 = load i32, i32* %2, align 4
  %54 = add nsw i32 %53, 1
  store i32 %54, i32* %2, align 4
  br label %5

55:
  store i32 0, i32* %2, align 4
  br label %56

56:
  %57 = load i32, i32* %2, align 4
  %58 = icmp slt i32 %57, 24
  br i1 %58, label %59, label %106

59:
  store i32 0, i32* %3, align 4
  br label %60

60:
  %61 = load i32, i32* %3, align 4
  %62 = icmp slt i32 %61, 24
  br i1 %62, label %63, label %103

63:
  %64 = load i32, i32* %2, align 4
  %65 = sext i32 %64 to i64
  %66 = load i32, i32* %3, align 4
  %67 = sext i32 %66 to i64
  %68 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @f, i64 0, i64 %65
  %69 = getelementptr inbounds [24 x i32], [24 x i32]* %68, i64 0, i64 %67
  store i32 0, i32* %69, align 4
  store i32 0, i32* %4, align 4
  br label %70

70:
  %71 = load i32, i32* %4, align 4
  %72 = icmp slt i32 %71, 24
  br i1 %72, label %73, label %100

73:
  %74 = load i32, i32* %2, align 4
  %75 = sext i32 %74 to i64
  %76 = load i32, i32* %4, align 4
  %77 = sext i32 %76 to i64
  %78 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @d, i64 0, i64 %75
  %79 = getelementptr inbounds [24 x i32], [24 x i32]* %78, i64 0, i64 %77
  %80 = load i32, i32* %79, align 4
  %81 = load i32, i32* %4, align 4
  %82 = sext i32 %81 to i64
  %83 = load i32, i32* %3, align 4
  %84 = sext i32 %83 to i64
  %85 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @e, i64 0, i64 %82
  %86 = getelementptr inbounds [24 x i32], [24 x i32]* %85, i64 0, i64 %84
  %87 = load i32, i32* %86, align 4
  %88 = mul nsw i32 %80, %87
  %89 = load i32, i32* %2, align 4
  %90 = sext i32 %89 to i64
  %91 = load i32, i32* %3, align 4
  %92 = sext i32 %91 to i64
  %93 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @f, i64 0, i64 %90
  %94 = getelementptr inbounds [24 x i32], [24 x i32]* %93, i64 0, i64 %92
  %95 = load i32, i32* %94, align 4
  %96 = add nsw i32 %95, %88
  store i32 %96, i32* %94, align 4
  br label %97

97:
  %98 = load i32, i32* %4, align 4
  %99 = add nsw i32 %98, 1
  store i32 %99, i32* %4, align 4
  br label %70

100:
  %101 = load i32, i32* %3, align 4
  %102 = add nsw i32 %101, 1
  store i32 %102, i32* %3, align 4
  br label %60

103:
  %104 = load i32, i32* %2, align 4
  %105 = add nsw i32 %104, 1
  store i32 %105, i32* %2, align 4
  br label %56

106:
  %107 = load i32, i32* %1, align 4
  ret i32 %107
}
attributes #0 = { nounwind }
