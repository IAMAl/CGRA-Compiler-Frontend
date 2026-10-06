; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@a = dso_local global [24 x [24 x double]] zeroinitializer, align 16
@b = dso_local global [24 x [24 x double]] zeroinitializer, align 16
@c = dso_local global [24 x [24 x double]] zeroinitializer, align 16
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
  br i1 %7, label %8, label %68

8:
  store i32 0, i32* %3, align 4
  br label %9

9:
  %10 = load i32, i32* %3, align 4
  %11 = icmp slt i32 %10, 24
  br i1 %11, label %12, label %65

12:
  %13 = load i32, i32* %2, align 4
  %14 = sext i32 %13 to i64
  %15 = load i32, i32* %3, align 4
  %16 = sext i32 %15 to i64
  %17 = getelementptr inbounds [24 x [24 x double]], [24 x [24 x double]]* @c, i64 0, i64 %14
  %18 = getelementptr inbounds [24 x double], [24 x double]* %17, i64 0, i64 %16
  store double 0.000000e+00, double* %18, align 4
  store i32 0, i32* %4, align 4
  br label %19

19:
  %20 = load i32, i32* %4, align 4
  %21 = icmp slt i32 %20, 24
  br i1 %21, label %22, label %62

22:
  %23 = load i32, i32* %2, align 4
  %24 = sext i32 %23 to i64
  %25 = load i32, i32* %4, align 4
  %26 = sext i32 %25 to i64
  %27 = getelementptr inbounds [24 x [24 x double]], [24 x [24 x double]]* @a, i64 0, i64 %24
  %28 = getelementptr inbounds [24 x double], [24 x double]* %27, i64 0, i64 %26
  %29 = load double, double* %28, align 4
  %30 = fcmp ogt double %29, 0.000000e+00
  br i1 %30, label %31, label %58

31:
  %32 = load i32, i32* %2, align 4
  %33 = sext i32 %32 to i64
  %34 = load i32, i32* %4, align 4
  %35 = sext i32 %34 to i64
  %36 = getelementptr inbounds [24 x [24 x double]], [24 x [24 x double]]* @a, i64 0, i64 %33
  %37 = getelementptr inbounds [24 x double], [24 x double]* %36, i64 0, i64 %35
  %38 = load double, double* %37, align 4
  %39 = load i32, i32* %4, align 4
  %40 = sext i32 %39 to i64
  %41 = load i32, i32* %3, align 4
  %42 = sext i32 %41 to i64
  %43 = getelementptr inbounds [24 x [24 x double]], [24 x [24 x double]]* @b, i64 0, i64 %40
  %44 = getelementptr inbounds [24 x double], [24 x double]* %43, i64 0, i64 %42
  %45 = load double, double* %44, align 4
  %46 = fmul double %38, %45
  %47 = load i32, i32* %4, align 4
  %48 = sitofp i32 %47 to double
  %49 = fadd double %46, %48
  %50 = load i32, i32* %2, align 4
  %51 = sext i32 %50 to i64
  %52 = load i32, i32* %3, align 4
  %53 = sext i32 %52 to i64
  %54 = getelementptr inbounds [24 x [24 x double]], [24 x [24 x double]]* @c, i64 0, i64 %51
  %55 = getelementptr inbounds [24 x double], [24 x double]* %54, i64 0, i64 %53
  %56 = load double, double* %55, align 4
  %57 = fadd double %56, %49
  store double %57, double* %55, align 4
  br label %58

58:
  br label %59

59:
  %60 = load i32, i32* %4, align 4
  %61 = add nsw i32 %60, 1
  store i32 %61, i32* %4, align 4
  br label %19

62:
  %63 = load i32, i32* %3, align 4
  %64 = add nsw i32 %63, 1
  store i32 %64, i32* %3, align 4
  br label %9

65:
  %66 = load i32, i32* %2, align 4
  %67 = add nsw i32 %66, 1
  store i32 %67, i32* %2, align 4
  br label %5

68:
  %69 = load i32, i32* %1, align 4
  ret i32 %69
}
attributes #0 = { nounwind }
