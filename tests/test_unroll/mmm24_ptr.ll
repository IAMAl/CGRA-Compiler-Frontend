; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
define dso_local void @kernel(i32* %a, i32* %b, i32* %c) #0 {
  %1 = alloca i32*, align 8
  %2 = alloca i32*, align 8
  %3 = alloca i32*, align 8
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  %6 = alloca i32, align 4
  store i32* %a, i32** %1, align 8
  store i32* %b, i32** %2, align 8
  store i32* %c, i32** %3, align 8
  store i32 0, i32* %4, align 4
  br label %7

7:
  %8 = load i32, i32* %4, align 4
  %9 = icmp slt i32 %8, 24
  br i1 %9, label %10, label %61

10:
  store i32 0, i32* %5, align 4
  br label %11

11:
  %12 = load i32, i32* %5, align 4
  %13 = icmp slt i32 %12, 24
  br i1 %13, label %14, label %58

14:
  %15 = load i32, i32* %4, align 4
  %16 = load i32, i32* %5, align 4
  %17 = load i32*, i32** %3, align 8
  %18 = mul nsw i32 %15, 24
  %19 = add nsw i32 %18, %16
  %20 = sext i32 %19 to i64
  %21 = getelementptr inbounds i32, i32* %17, i64 %20
  store i32 0, i32* %21, align 4
  store i32 0, i32* %6, align 4
  br label %22

22:
  %23 = load i32, i32* %6, align 4
  %24 = icmp slt i32 %23, 24
  br i1 %24, label %25, label %55

25:
  %26 = load i32, i32* %4, align 4
  %27 = load i32, i32* %6, align 4
  %28 = load i32*, i32** %1, align 8
  %29 = mul nsw i32 %26, 24
  %30 = add nsw i32 %29, %27
  %31 = sext i32 %30 to i64
  %32 = getelementptr inbounds i32, i32* %28, i64 %31
  %33 = load i32, i32* %32, align 4
  %34 = load i32, i32* %6, align 4
  %35 = load i32, i32* %5, align 4
  %36 = load i32*, i32** %2, align 8
  %37 = mul nsw i32 %34, 24
  %38 = add nsw i32 %37, %35
  %39 = sext i32 %38 to i64
  %40 = getelementptr inbounds i32, i32* %36, i64 %39
  %41 = load i32, i32* %40, align 4
  %42 = mul nsw i32 %33, %41
  %43 = load i32, i32* %4, align 4
  %44 = load i32, i32* %5, align 4
  %45 = load i32*, i32** %3, align 8
  %46 = mul nsw i32 %43, 24
  %47 = add nsw i32 %46, %44
  %48 = sext i32 %47 to i64
  %49 = getelementptr inbounds i32, i32* %45, i64 %48
  %50 = load i32, i32* %49, align 4
  %51 = add nsw i32 %50, %42
  store i32 %51, i32* %49, align 4
  br label %52

52:
  %53 = load i32, i32* %6, align 4
  %54 = add nsw i32 %53, 1
  store i32 %54, i32* %6, align 4
  br label %22

55:
  %56 = load i32, i32* %5, align 4
  %57 = add nsw i32 %56, 1
  store i32 %57, i32* %5, align 4
  br label %11

58:
  %59 = load i32, i32* %4, align 4
  %60 = add nsw i32 %59, 1
  store i32 %60, i32* %4, align 4
  br label %7

61:
  ret void
}
attributes #0 = { nounwind }
