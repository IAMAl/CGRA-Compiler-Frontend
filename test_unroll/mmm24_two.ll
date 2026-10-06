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
  br i1 %7, label %8, label %84

8:
  store i32 0, i32* %3, align 4
  br label %9

9:
  %10 = load i32, i32* %3, align 4
  %11 = icmp slt i32 %10, 24
  br i1 %11, label %12, label %81

12:
  %13 = load i32, i32* %2, align 4
  %14 = sext i32 %13 to i64
  %15 = load i32, i32* %3, align 4
  %16 = sext i32 %15 to i64
  %17 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %14
  %18 = getelementptr inbounds [24 x i32], [24 x i32]* %17, i64 0, i64 %16
  store i32 0, i32* %18, align 4
  %19 = load i32, i32* %2, align 4
  %20 = sext i32 %19 to i64
  %21 = load i32, i32* %3, align 4
  %22 = sext i32 %21 to i64
  %23 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @f, i64 0, i64 %20
  %24 = getelementptr inbounds [24 x i32], [24 x i32]* %23, i64 0, i64 %22
  store i32 0, i32* %24, align 4
  store i32 0, i32* %4, align 4
  br label %25

25:
  %26 = load i32, i32* %4, align 4
  %27 = icmp slt i32 %26, 24
  br i1 %27, label %28, label %78

28:
  %29 = load i32, i32* %2, align 4
  %30 = sext i32 %29 to i64
  %31 = load i32, i32* %4, align 4
  %32 = sext i32 %31 to i64
  %33 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %30
  %34 = getelementptr inbounds [24 x i32], [24 x i32]* %33, i64 0, i64 %32
  %35 = load i32, i32* %34, align 4
  %36 = load i32, i32* %4, align 4
  %37 = sext i32 %36 to i64
  %38 = load i32, i32* %3, align 4
  %39 = sext i32 %38 to i64
  %40 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %37
  %41 = getelementptr inbounds [24 x i32], [24 x i32]* %40, i64 0, i64 %39
  %42 = load i32, i32* %41, align 4
  %43 = mul nsw i32 %35, %42
  %44 = load i32, i32* %2, align 4
  %45 = sext i32 %44 to i64
  %46 = load i32, i32* %3, align 4
  %47 = sext i32 %46 to i64
  %48 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %45
  %49 = getelementptr inbounds [24 x i32], [24 x i32]* %48, i64 0, i64 %47
  %50 = load i32, i32* %49, align 4
  %51 = add nsw i32 %50, %43
  store i32 %51, i32* %49, align 4
  %52 = load i32, i32* %2, align 4
  %53 = sext i32 %52 to i64
  %54 = load i32, i32* %4, align 4
  %55 = sext i32 %54 to i64
  %56 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @d, i64 0, i64 %53
  %57 = getelementptr inbounds [24 x i32], [24 x i32]* %56, i64 0, i64 %55
  %58 = load i32, i32* %57, align 4
  %59 = load i32, i32* %4, align 4
  %60 = sext i32 %59 to i64
  %61 = load i32, i32* %3, align 4
  %62 = sext i32 %61 to i64
  %63 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @e, i64 0, i64 %60
  %64 = getelementptr inbounds [24 x i32], [24 x i32]* %63, i64 0, i64 %62
  %65 = load i32, i32* %64, align 4
  %66 = mul nsw i32 %58, %65
  %67 = load i32, i32* %2, align 4
  %68 = sext i32 %67 to i64
  %69 = load i32, i32* %3, align 4
  %70 = sext i32 %69 to i64
  %71 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @f, i64 0, i64 %68
  %72 = getelementptr inbounds [24 x i32], [24 x i32]* %71, i64 0, i64 %70
  %73 = load i32, i32* %72, align 4
  %74 = add nsw i32 %73, %66
  store i32 %74, i32* %72, align 4
  br label %75

75:
  %76 = load i32, i32* %4, align 4
  %77 = add nsw i32 %76, 1
  store i32 %77, i32* %4, align 4
  br label %25

78:
  %79 = load i32, i32* %3, align 4
  %80 = add nsw i32 %79, 1
  store i32 %80, i32* %3, align 4
  br label %9

81:
  %82 = load i32, i32* %2, align 4
  %83 = add nsw i32 %82, 1
  store i32 %83, i32* %2, align 4
  br label %5

84:
  %85 = load i32, i32* %1, align 4
  ret i32 %85
}
attributes #0 = { nounwind }
