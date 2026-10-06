; ModuleID = 'straight.cc'
source_filename = "straight.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@a = dso_local global [8 x i32] zeroinitializer, align 16
@b = dso_local global [8 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16
; Function Attrs: mustprogress noinline norecurse nounwind optnone uwtable
define dso_local noundef i32 @main() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  %2 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 0
  %3 = load i32, i32* %2, align 4
  %4 = getelementptr inbounds [8 x i32], [8 x i32]* @b, i64 0, i64 0
  %5 = load i32, i32* %4, align 4
  %6 = mul nsw i32 %3, %5
  %7 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 1
  %8 = load i32, i32* %7, align 4
  %9 = getelementptr inbounds [8 x i32], [8 x i32]* @b, i64 0, i64 1
  %10 = load i32, i32* %9, align 4
  %11 = mul nsw i32 %8, %10
  %12 = add nsw i32 %6, %11
  %13 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 0
  store i32 %12, i32* %13, align 4
  %14 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 2
  %15 = load i32, i32* %14, align 4
  %16 = getelementptr inbounds [8 x i32], [8 x i32]* @b, i64 0, i64 2
  %17 = load i32, i32* %16, align 4
  %18 = add nsw i32 %15, %17
  %19 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 1
  store i32 %18, i32* %19, align 4
  %20 = load i32, i32* %1, align 4
  ret i32 %20
}
attributes #0 = { nounwind }
