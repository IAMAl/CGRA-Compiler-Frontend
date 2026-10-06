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
@v = dso_local global [24 x i32] zeroinitializer, align 16
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
  br i1 %7, label %8, label %135

8:
  %9 = load i32, i32* %2, align 4
  %10 = add nsw i32 %9, 7
  %11 = load i32, i32* %2, align 4
  %12 = sext i32 %11 to i64
  %13 = getelementptr inbounds [24 x i32], [24 x i32]* @v, i64 0, i64 %12
  store i32 %10, i32* %13, align 4
  store i32 0, i32* %3, align 4
  br label %14

14:
  %15 = load i32, i32* %3, align 4
  %16 = icmp slt i32 %15, 24
  br i1 %16, label %17, label %132

17:
  %18 = load i32, i32* %2, align 4
  %19 = sext i32 %18 to i64
  %20 = load i32, i32* %3, align 4
  %21 = sext i32 %20 to i64
  %22 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %19
  %23 = getelementptr inbounds [24 x i32], [24 x i32]* %22, i64 0, i64 %21
  store i32 0, i32* %23, align 4
  %24 = load i32, i32* %2, align 4
  %25 = sext i32 %24 to i64
  %26 = load i32, i32* %3, align 4
  %27 = sext i32 %26 to i64
  %28 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @f, i64 0, i64 %25
  %29 = getelementptr inbounds [24 x i32], [24 x i32]* %28, i64 0, i64 %27
  store i32 0, i32* %29, align 4
  store i32 0, i32* %4, align 4
  br label %30

30:
  %31 = load i32, i32* %4, align 4
  %32 = icmp slt i32 %31, 24
  br i1 %32, label %33, label %129

33:
  %34 = load i32, i32* %2, align 4
  %35 = sext i32 %34 to i64
  %36 = load i32, i32* %4, align 4
  %37 = sext i32 %36 to i64
  %38 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %35
  %39 = getelementptr inbounds [24 x i32], [24 x i32]* %38, i64 0, i64 %37
  %40 = load i32, i32* %39, align 4
  %41 = load i32, i32* %4, align 4
  %42 = sext i32 %41 to i64
  %43 = load i32, i32* %3, align 4
  %44 = sext i32 %43 to i64
  %45 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %42
  %46 = getelementptr inbounds [24 x i32], [24 x i32]* %45, i64 0, i64 %44
  %47 = load i32, i32* %46, align 4
  %48 = mul nsw i32 %40, %47
  %49 = load i32, i32* %2, align 4
  %50 = sext i32 %49 to i64
  %51 = load i32, i32* %4, align 4
  %52 = add nsw i32 %51, 1
  %53 = sext i32 %52 to i64
  %54 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %50
  %55 = getelementptr inbounds [24 x i32], [24 x i32]* %54, i64 0, i64 %53
  %56 = load i32, i32* %55, align 4
  %57 = load i32, i32* %4, align 4
  %58 = add nsw i32 %57, 1
  %59 = sext i32 %58 to i64
  %60 = load i32, i32* %3, align 4
  %61 = sext i32 %60 to i64
  %62 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %59
  %63 = getelementptr inbounds [24 x i32], [24 x i32]* %62, i64 0, i64 %61
  %64 = load i32, i32* %63, align 4
  %65 = mul nsw i32 %56, %64
  %66 = add nsw i32 %48, %65
  %67 = load i32, i32* %2, align 4
  %68 = sext i32 %67 to i64
  %69 = getelementptr inbounds [24 x i32], [24 x i32]* @v, i64 0, i64 %68
  %70 = load i32, i32* %69, align 4
  %71 = mul nsw i32 %66, %70
  %72 = load i32, i32* %2, align 4
  %73 = sext i32 %72 to i64
  %74 = load i32, i32* %3, align 4
  %75 = sext i32 %74 to i64
  %76 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %73
  %77 = getelementptr inbounds [24 x i32], [24 x i32]* %76, i64 0, i64 %75
  %78 = load i32, i32* %77, align 4
  %79 = add nsw i32 %78, %71
  store i32 %79, i32* %77, align 4
  %80 = load i32, i32* %2, align 4
  %81 = sext i32 %80 to i64
  %82 = load i32, i32* %4, align 4
  %83 = sext i32 %82 to i64
  %84 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @d, i64 0, i64 %81
  %85 = getelementptr inbounds [24 x i32], [24 x i32]* %84, i64 0, i64 %83
  %86 = load i32, i32* %85, align 4
  %87 = load i32, i32* %4, align 4
  %88 = sext i32 %87 to i64
  %89 = load i32, i32* %3, align 4
  %90 = sext i32 %89 to i64
  %91 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @e, i64 0, i64 %88
  %92 = getelementptr inbounds [24 x i32], [24 x i32]* %91, i64 0, i64 %90
  %93 = load i32, i32* %92, align 4
  %94 = mul nsw i32 %86, %93
  %95 = load i32, i32* %2, align 4
  %96 = sext i32 %95 to i64
  %97 = load i32, i32* %4, align 4
  %98 = add nsw i32 %97, 1
  %99 = sext i32 %98 to i64
  %100 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @d, i64 0, i64 %96
  %101 = getelementptr inbounds [24 x i32], [24 x i32]* %100, i64 0, i64 %99
  %102 = load i32, i32* %101, align 4
  %103 = load i32, i32* %4, align 4
  %104 = add nsw i32 %103, 1
  %105 = sext i32 %104 to i64
  %106 = load i32, i32* %3, align 4
  %107 = sext i32 %106 to i64
  %108 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @e, i64 0, i64 %105
  %109 = getelementptr inbounds [24 x i32], [24 x i32]* %108, i64 0, i64 %107
  %110 = load i32, i32* %109, align 4
  %111 = mul nsw i32 %102, %110
  %112 = add nsw i32 %94, %111
  %113 = load i32, i32* %2, align 4
  %114 = sext i32 %113 to i64
  %115 = getelementptr inbounds [24 x i32], [24 x i32]* @v, i64 0, i64 %114
  %116 = load i32, i32* %115, align 4
  %117 = mul nsw i32 %112, %116
  %118 = load i32, i32* %2, align 4
  %119 = sext i32 %118 to i64
  %120 = load i32, i32* %3, align 4
  %121 = sext i32 %120 to i64
  %122 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @f, i64 0, i64 %119
  %123 = getelementptr inbounds [24 x i32], [24 x i32]* %122, i64 0, i64 %121
  %124 = load i32, i32* %123, align 4
  %125 = add nsw i32 %124, %117
  store i32 %125, i32* %123, align 4
  br label %126

126:
  %127 = load i32, i32* %4, align 4
  %128 = add nsw i32 %127, 2
  store i32 %128, i32* %4, align 4
  br label %30

129:
  %130 = load i32, i32* %3, align 4
  %131 = add nsw i32 %130, 1
  store i32 %131, i32* %3, align 4
  br label %14

132:
  %133 = load i32, i32* %2, align 4
  %134 = add nsw i32 %133, 1
  store i32 %134, i32* %2, align 4
  br label %5

135:
  %136 = load i32, i32* %1, align 4
  ret i32 %136
}
attributes #0 = { nounwind }
