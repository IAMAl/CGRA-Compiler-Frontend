; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@a = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@b = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@c = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
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
  br i1 %7, label %8, label %65

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
  br i1 %16, label %17, label %62

17:
  %18 = load i32, i32* %2, align 4
  %19 = sext i32 %18 to i64
  %20 = load i32, i32* %3, align 4
  %21 = sext i32 %20 to i64
  %22 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %19
  %23 = getelementptr inbounds [24 x i32], [24 x i32]* %22, i64 0, i64 %21
  store i32 0, i32* %23, align 4
  store i32 0, i32* %4, align 4
  br label %24

24:
  %25 = load i32, i32* %4, align 4
  %26 = icmp slt i32 %25, 24
  br i1 %26, label %27, label %59

27:
  %28 = load i32, i32* %2, align 4
  %29 = sext i32 %28 to i64
  %30 = load i32, i32* %4, align 4
  %31 = sext i32 %30 to i64
  %32 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %29
  %33 = getelementptr inbounds [24 x i32], [24 x i32]* %32, i64 0, i64 %31
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
  %45 = getelementptr inbounds [24 x i32], [24 x i32]* @v, i64 0, i64 %44
  %46 = load i32, i32* %45, align 4
  %47 = mul nsw i32 %42, %46
  %48 = load i32, i32* %2, align 4
  %49 = sext i32 %48 to i64
  %50 = load i32, i32* %3, align 4
  %51 = sext i32 %50 to i64
  %52 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %49
  %53 = getelementptr inbounds [24 x i32], [24 x i32]* %52, i64 0, i64 %51
  %54 = load i32, i32* %53, align 4
  %55 = add nsw i32 %54, %47
  store i32 %55, i32* %53, align 4
  br label %56

56:
  %57 = load i32, i32* %4, align 4
  %58 = add nsw i32 %57, 1
  store i32 %58, i32* %4, align 4
  br label %24

59:
  %60 = load i32, i32* %3, align 4
  %61 = add nsw i32 %60, 1
  store i32 %61, i32* %3, align 4
  br label %14

62:
  %63 = load i32, i32* %2, align 4
  %64 = add nsw i32 %63, 1
  store i32 %64, i32* %2, align 4
  br label %5

65:
  %66 = load i32, i32* %1, align 4
  ret i32 %66
}
attributes #0 = { nounwind }
