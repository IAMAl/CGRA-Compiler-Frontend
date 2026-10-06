; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@a = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@b = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@c = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
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
  br i1 %15, label %16, label %63

16:
  store i32 0, i32* %3, align 4
  br label %17

17:
  %18 = load i32, i32* %3, align 4
  %19 = icmp slt i32 %18, 24
  br i1 %19, label %20, label %60

20:
  %21 = load i32, i32* %2, align 4
  %22 = sext i32 %21 to i64
  %23 = load i32, i32* %3, align 4
  %24 = sext i32 %23 to i64
  %25 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %22
  %26 = getelementptr inbounds [24 x i32], [24 x i32]* %25, i64 0, i64 %24
  store i32 0, i32* %26, align 4
  store i32 0, i32* %4, align 4
  br label %27

27:
  %28 = load i32, i32* %4, align 4
  %29 = icmp slt i32 %28, 24
  br i1 %29, label %30, label %57

30:
  %31 = load i32, i32* %2, align 4
  %32 = sext i32 %31 to i64
  %33 = load i32, i32* %4, align 4
  %34 = sext i32 %33 to i64
  %35 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %32
  %36 = getelementptr inbounds [24 x i32], [24 x i32]* %35, i64 0, i64 %34
  %37 = load i32, i32* %36, align 4
  %38 = load i32, i32* %4, align 4
  %39 = sext i32 %38 to i64
  %40 = load i32, i32* %3, align 4
  %41 = sext i32 %40 to i64
  %42 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %39
  %43 = getelementptr inbounds [24 x i32], [24 x i32]* %42, i64 0, i64 %41
  %44 = load i32, i32* %43, align 4
  %45 = mul nsw i32 %37, %44
  %46 = load i32, i32* %2, align 4
  %47 = sext i32 %46 to i64
  %48 = load i32, i32* %3, align 4
  %49 = sext i32 %48 to i64
  %50 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %47
  %51 = getelementptr inbounds [24 x i32], [24 x i32]* %50, i64 0, i64 %49
  %52 = load i32, i32* %51, align 4
  %53 = add nsw i32 %52, %45
  store i32 %53, i32* %51, align 4
  br label %54

54:
  %55 = load i32, i32* %4, align 4
  %56 = add nsw i32 %55, 1
  store i32 %56, i32* %4, align 4
  br label %27

57:
  %58 = load i32, i32* %3, align 4
  %59 = add nsw i32 %58, 1
  store i32 %59, i32* %3, align 4
  br label %17

60:
  %61 = load i32, i32* %2, align 4
  %62 = add nsw i32 %61, 1
  store i32 %62, i32* %2, align 4
  br label %13

63:
  %64 = getelementptr inbounds [24 x i32], [24 x i32]* @p, i64 0, i64 0
  %65 = load i32, i32* %64, align 4
  %66 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 0
  %67 = getelementptr inbounds [24 x i32], [24 x i32]* %66, i64 0, i64 0
  %68 = load i32, i32* %67, align 4
  %69 = add nsw i32 %65, %68
  %70 = getelementptr inbounds [24 x i32], [24 x i32]* @p, i64 0, i64 1
  store i32 %69, i32* %70, align 4
  %71 = load i32, i32* %1, align 4
  ret i32 %71
}
attributes #0 = { nounwind }
