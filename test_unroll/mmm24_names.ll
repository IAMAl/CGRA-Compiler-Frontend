; ModuleID = 'mmm.cc'
source_filename = "mmm.cc"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@a = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@b = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@c = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
define dso_local noundef i32 @main() #0 {
entry:
  %retval = alloca i32, align 4
  %i = alloca i32, align 4
  %j = alloca i32, align 4
  %k = alloca i32, align 4
  store i32 0, i32* %retval, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond.i

for.cond.i:
  %0 = load i32, i32* %i, align 4
  %1 = icmp slt i32 %0, 24
  br i1 %1, label %for.body.i, label %for.end.i

for.body.i:
  store i32 0, i32* %j, align 4
  br label %for.cond.j

for.cond.j:
  %2 = load i32, i32* %j, align 4
  %3 = icmp slt i32 %2, 24
  br i1 %3, label %for.body.j, label %for.inc.i

for.body.j:
  %4 = load i32, i32* %i, align 4
  %5 = sext i32 %4 to i64
  %6 = load i32, i32* %j, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %5
  %9 = getelementptr inbounds [24 x i32], [24 x i32]* %8, i64 0, i64 %7
  store i32 0, i32* %9, align 4
  store i32 0, i32* %k, align 4
  br label %for.cond.k

for.cond.k:
  %10 = load i32, i32* %k, align 4
  %11 = icmp slt i32 %10, 24
  br i1 %11, label %for.body.k, label %for.inc.j

for.body.k:
  %12 = load i32, i32* %i, align 4
  %13 = sext i32 %12 to i64
  %14 = load i32, i32* %k, align 4
  %15 = sext i32 %14 to i64
  %16 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %13
  %17 = getelementptr inbounds [24 x i32], [24 x i32]* %16, i64 0, i64 %15
  %18 = load i32, i32* %17, align 4
  %19 = load i32, i32* %k, align 4
  %20 = sext i32 %19 to i64
  %21 = load i32, i32* %j, align 4
  %22 = sext i32 %21 to i64
  %23 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @b, i64 0, i64 %20
  %24 = getelementptr inbounds [24 x i32], [24 x i32]* %23, i64 0, i64 %22
  %25 = load i32, i32* %24, align 4
  %26 = mul nsw i32 %18, %25
  %27 = load i32, i32* %i, align 4
  %28 = sext i32 %27 to i64
  %29 = load i32, i32* %j, align 4
  %30 = sext i32 %29 to i64
  %31 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @c, i64 0, i64 %28
  %32 = getelementptr inbounds [24 x i32], [24 x i32]* %31, i64 0, i64 %30
  %33 = load i32, i32* %32, align 4
  %34 = add nsw i32 %33, %26
  store i32 %34, i32* %32, align 4
  br label %for.inc.k

for.inc.k:
  %35 = load i32, i32* %k, align 4
  %36 = add nsw i32 %35, 1
  store i32 %36, i32* %k, align 4
  br label %for.cond.k

for.inc.j:
  %37 = load i32, i32* %j, align 4
  %38 = add nsw i32 %37, 1
  store i32 %38, i32* %j, align 4
  br label %for.cond.j

for.inc.i:
  %39 = load i32, i32* %i, align 4
  %40 = add nsw i32 %39, 1
  store i32 %40, i32* %i, align 4
  br label %for.cond.i

for.end.i:
  %41 = load i32, i32* %retval, align 4
  ret i32 %41
}
attributes #0 = { nounwind }
