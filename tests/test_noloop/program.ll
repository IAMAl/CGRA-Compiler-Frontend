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
@p = dso_local global [24 x i32] zeroinitializer, align 16
define dso_local noundef i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  %5 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 0
  %6 = getelementptr inbounds [24 x i32], [24 x i32]* %5, i64 0, i64 0
  %7 = load i32, i32* %6, align 4
  %8 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 0
  %9 = getelementptr inbounds [24 x i32], [24 x i32]* %8, i64 0, i64 0
  %10 = load i32, i32* %9, align 4
  %11 = mul nsw i32 %7, %10
  %12 = getelementptr inbounds [24 x i32], [24 x i32]* @p, i64 0, i64 0
  store i32 %11, i32* %12, align 4
  store i32 0, i32* %2, align 4
  br label %13

13:
  %14 = load i32, i32* %2, align 4
  %15 = icmp slt i32 %14, 24
  br i1 %15, label %16, label %143

16:
  %17 = load i32, i32* %2, align 4
  %18 = add nsw i32 %17, 7
  %19 = load i32, i32* %2, align 4
  %20 = sext i32 %19 to i64
  %21 = getelementptr inbounds [24 x i32], [24 x i32]* @v, i64 0, i64 %20
  store i32 %18, i32* %21, align 4
  store i32 0, i32* %3, align 4
  br label %22

22:
  %23 = load i32, i32* %3, align 4
  %24 = icmp slt i32 %23, 24
  br i1 %24, label %25, label %140

25:
  %26 = load i32, i32* %2, align 4
  %27 = sext i32 %26 to i64
  %28 = load i32, i32* %3, align 4
  %29 = sext i32 %28 to i64
  %30 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %27
  %31 = getelementptr inbounds [24 x i32], [24 x i32]* %30, i64 0, i64 %29
  store i32 0, i32* %31, align 4
  %32 = load i32, i32* %2, align 4
  %33 = sext i32 %32 to i64
  %34 = load i32, i32* %3, align 4
  %35 = sext i32 %34 to i64
  %36 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @f, i64 0, i64 %33
  %37 = getelementptr inbounds [24 x i32], [24 x i32]* %36, i64 0, i64 %35
  store i32 0, i32* %37, align 4
  store i32 0, i32* %4, align 4
  br label %38

38:
  %39 = load i32, i32* %4, align 4
  %40 = icmp slt i32 %39, 24
  br i1 %40, label %41, label %137

41:
  %42 = load i32, i32* %2, align 4
  %43 = sext i32 %42 to i64
  %44 = load i32, i32* %4, align 4
  %45 = sext i32 %44 to i64
  %46 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %43
  %47 = getelementptr inbounds [24 x i32], [24 x i32]* %46, i64 0, i64 %45
  %48 = load i32, i32* %47, align 4
  %49 = load i32, i32* %4, align 4
  %50 = sext i32 %49 to i64
  %51 = load i32, i32* %3, align 4
  %52 = sext i32 %51 to i64
  %53 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %50
  %54 = getelementptr inbounds [24 x i32], [24 x i32]* %53, i64 0, i64 %52
  %55 = load i32, i32* %54, align 4
  %56 = mul nsw i32 %48, %55
  %57 = load i32, i32* %2, align 4
  %58 = sext i32 %57 to i64
  %59 = load i32, i32* %4, align 4
  %60 = add nsw i32 %59, 1
  %61 = sext i32 %60 to i64
  %62 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %58
  %63 = getelementptr inbounds [24 x i32], [24 x i32]* %62, i64 0, i64 %61
  %64 = load i32, i32* %63, align 4
  %65 = load i32, i32* %4, align 4
  %66 = add nsw i32 %65, 1
  %67 = sext i32 %66 to i64
  %68 = load i32, i32* %3, align 4
  %69 = sext i32 %68 to i64
  %70 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %67
  %71 = getelementptr inbounds [24 x i32], [24 x i32]* %70, i64 0, i64 %69
  %72 = load i32, i32* %71, align 4
  %73 = mul nsw i32 %64, %72
  %74 = add nsw i32 %56, %73
  %75 = load i32, i32* %2, align 4
  %76 = sext i32 %75 to i64
  %77 = getelementptr inbounds [24 x i32], [24 x i32]* @v, i64 0, i64 %76
  %78 = load i32, i32* %77, align 4
  %79 = mul nsw i32 %74, %78
  %80 = load i32, i32* %2, align 4
  %81 = sext i32 %80 to i64
  %82 = load i32, i32* %3, align 4
  %83 = sext i32 %82 to i64
  %84 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %81
  %85 = getelementptr inbounds [24 x i32], [24 x i32]* %84, i64 0, i64 %83
  %86 = load i32, i32* %85, align 4
  %87 = add nsw i32 %86, %79
  store i32 %87, i32* %85, align 4
  %88 = load i32, i32* %2, align 4
  %89 = sext i32 %88 to i64
  %90 = load i32, i32* %4, align 4
  %91 = sext i32 %90 to i64
  %92 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @d, i64 0, i64 %89
  %93 = getelementptr inbounds [24 x i32], [24 x i32]* %92, i64 0, i64 %91
  %94 = load i32, i32* %93, align 4
  %95 = load i32, i32* %4, align 4
  %96 = sext i32 %95 to i64
  %97 = load i32, i32* %3, align 4
  %98 = sext i32 %97 to i64
  %99 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @e, i64 0, i64 %96
  %100 = getelementptr inbounds [24 x i32], [24 x i32]* %99, i64 0, i64 %98
  %101 = load i32, i32* %100, align 4
  %102 = mul nsw i32 %94, %101
  %103 = load i32, i32* %2, align 4
  %104 = sext i32 %103 to i64
  %105 = load i32, i32* %4, align 4
  %106 = add nsw i32 %105, 1
  %107 = sext i32 %106 to i64
  %108 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @d, i64 0, i64 %104
  %109 = getelementptr inbounds [24 x i32], [24 x i32]* %108, i64 0, i64 %107
  %110 = load i32, i32* %109, align 4
  %111 = load i32, i32* %4, align 4
  %112 = add nsw i32 %111, 1
  %113 = sext i32 %112 to i64
  %114 = load i32, i32* %3, align 4
  %115 = sext i32 %114 to i64
  %116 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @e, i64 0, i64 %113
  %117 = getelementptr inbounds [24 x i32], [24 x i32]* %116, i64 0, i64 %115
  %118 = load i32, i32* %117, align 4
  %119 = mul nsw i32 %110, %118
  %120 = add nsw i32 %102, %119
  %121 = load i32, i32* %2, align 4
  %122 = sext i32 %121 to i64
  %123 = getelementptr inbounds [24 x i32], [24 x i32]* @v, i64 0, i64 %122
  %124 = load i32, i32* %123, align 4
  %125 = mul nsw i32 %120, %124
  %126 = load i32, i32* %2, align 4
  %127 = sext i32 %126 to i64
  %128 = load i32, i32* %3, align 4
  %129 = sext i32 %128 to i64
  %130 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @f, i64 0, i64 %127
  %131 = getelementptr inbounds [24 x i32], [24 x i32]* %130, i64 0, i64 %129
  %132 = load i32, i32* %131, align 4
  %133 = add nsw i32 %132, %125
  store i32 %133, i32* %131, align 4
  br label %134

134:
  %135 = load i32, i32* %4, align 4
  %136 = add nsw i32 %135, 2
  store i32 %136, i32* %4, align 4
  br label %38

137:
  %138 = load i32, i32* %3, align 4
  %139 = add nsw i32 %138, 1
  store i32 %139, i32* %3, align 4
  br label %22

140:
  %141 = load i32, i32* %2, align 4
  %142 = add nsw i32 %141, 1
  store i32 %142, i32* %2, align 4
  br label %13

143:
  %144 = getelementptr inbounds [24 x i32], [24 x i32]* @p, i64 0, i64 0
  %145 = load i32, i32* %144, align 4
  %146 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 0
  %147 = getelementptr inbounds [24 x i32], [24 x i32]* %146, i64 0, i64 0
  %148 = load i32, i32* %147, align 4
  %149 = add nsw i32 %145, %148
  %150 = getelementptr inbounds [24 x i32], [24 x i32]* @p, i64 0, i64 1
  store i32 %149, i32* %150, align 4
  %151 = load i32, i32* %1, align 4
  ret i32 %151
}
attributes #0 = { nounwind }
